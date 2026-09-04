#!/usr/bin/env python3
"""GTA San Andreas (PS2 일본판 SLPM-65984) 세이브 정화 도구
검열판에서 만든 세이브의 데이트 진입 플래그($131C=0)를 1로 고친다.
입력: PCSX2 메모리카드(.ps2, ECC 유무 무관) 또는 세이브 파일 단독(*.b, 202752B)
사용: python gtasa_save_fix.py Mcd001.ps2   → Mcd001.ps2 덮어쓰기, 원본은 Mcd001.ps2.bak
"""
import struct, sys, os, shutil
SAVE_LEN=202752; OFF=0x14D6; ANCHOR=(0x14EE,b'NIL'); GAMEDIR='BISLPM-65984GTA'
par=[bin(i).count('1')&1 for i in range(256)]
cpm=[0x55,0x33,0x0F,0x00,0xAA,0xCC,0xF0]
cpmask=[sum(par[b&m]<<j for j,m in enumerate(cpm)) for b in range(256)]
def ecc128(s):
    cp=0x77;l0=0x7f;l1=0x7f
    for i,b in enumerate(s):
        cp^=cpmask[b]
        if par[b]: l0^=~i;l1^=i
    return bytes([cp&0xff,l0&0x7f,l1&0xff])
def ecc_page(pg): return b''.join(ecc128(pg[i:i+128]) for i in range(0,len(pg),128)).ljust(16,b'\0')

def fix_save(d):
    """d: bytearray 세이브. 반환 (변경여부, 메시지)"""
    if len(d)!=SAVE_LEN: return False,'크기 불일치 %d'%len(d)
    if d[ANCHOR[0]:ANCHOR[0]+3]!=ANCHOR[1]: return False,'앵커 불일치(다른 리전/버전 세이브?)'
    v=struct.unpack_from('<I',d,OFF)[0]
    if v==1: return False,'이미 정상(131C=1)'
    if v!=0: return False,'131C 예상외 값 %d'%v
    d[OFF]=1
    struct.pack_into('<I',d,SAVE_LEN-4,sum(d[:-4])&0xffffffff)
    return True,'131C 0→1, 체크섬 갱신'

class MC:
    def __init__(s,d):
        s.d=d; h=d[:0x200]
        if not h.startswith(b'Sony PS2 Memory Card Format'): raise ValueError('PS2 메모리카드 아님')
        s.page_len=struct.unpack_from('<H',h,0x28)[0]; s.ppc=struct.unpack_from('<H',h,0x2a)[0]
        s.cpc=struct.unpack_from('<I',h,0x30)[0]; s.alloc_off=struct.unpack_from('<I',h,0x34)[0]
        s.rootdir=struct.unpack_from('<I',h,0x3c)[0]
        s.ifc=[x for x in struct.unpack_from('<32I',h,0x50) if x not in(0,0xffffffff)]
        npages=s.cpc*s.ppc
        if len(d)==npages*(s.page_len+16): s.raw=s.page_len+16
        elif len(d)==npages*s.page_len: s.raw=s.page_len
        else: raise ValueError('크기 불일치')
        s.csize=s.page_len*s.ppc
        fat=[]
        for ifc in s.ifc:
            for fc in struct.unpack('<%dI'%(s.csize//4),s.cluster(fc:=None) if False else s.cluster(ifc)):
                if fc==0xffffffff: continue
                fat+=list(struct.unpack('<%dI'%(s.csize//4),s.cluster(fc)))
        s.fat=fat
    def page(s,p): o=p*s.raw; return s.d[o:o+s.page_len]
    def cluster(s,c): return b''.join(s.page(c*s.ppc+i) for i in range(s.ppc))
    def chain(s,c):
        out=[]
        while c not in(0xffffffff,0x7fffffff):
            out.append(c); n=s.fat[c]
            if not n&0x80000000: break
            c=n&0x7fffffff
        return out
    def file_pages(s,c): return [(s.alloc_off+cl)*s.ppc+i for cl in s.chain(c) for i in range(s.ppc)]
    def listdir(s,c):
        for p in s.file_pages(c):
            pg=s.page(p); mode=struct.unpack_from('<H',pg,0)[0]
            if mode in(0,0xffff): continue
            yield mode,struct.unpack_from('<I',pg,4)[0],struct.unpack_from('<I',pg,0x10)[0],pg[0x40:0x60].split(b'\0')[0].decode('latin1')
    def write_pages(s,pages,data):
        for i,p in enumerate(pages):
            pg=bytes(data[i*s.page_len:(i+1)*s.page_len]).ljust(s.page_len,b'\0'); o=p*s.raw
            s.d[o:o+s.page_len]=pg
            if s.raw>s.page_len: s.d[o+s.page_len:o+s.raw]=ecc_page(pg)

def process(path):
    d=bytearray(open(path,'rb').read()); changed=0
    if len(d)==SAVE_LEN:
        ok,msg=fix_save(d); print(os.path.basename(path),msg); changed=ok
    else:
        mc=MC(d); found=False
        for mode,ln,cl,name in mc.listdir(mc.rootdir):
            if not(mode&0x20 and name.startswith(GAMEDIR)): continue
            found=True
            for m2,ln2,cl2,n2 in mc.listdir(cl):
                if not(m2&0x10 and ln2==SAVE_LEN): continue
                pages=mc.file_pages(cl2); sd=bytearray(b''.join(mc.page(p) for p in pages)[:ln2])
                ok,msg=fix_save(sd); print(' ',n2,'->',msg)
                if ok: mc.write_pages(pages,sd); changed+=1
        if not found: print('GTA SA(SLPM-65984) 세이브 없음')
    if changed:
        bak=path+'.bak'
        if not os.path.exists(bak): shutil.copy2(path,bak)
        open(path,'wb').write(d); print('저장 완료 (백업: %s)'%bak)
    else: print('변경 없음')

if __name__=='__main__':
    if len(sys.argv)<2: print(__doc__); sys.exit(1)
    for p in sys.argv[1:]: process(p)
