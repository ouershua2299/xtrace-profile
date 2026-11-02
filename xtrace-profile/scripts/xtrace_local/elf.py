"""CUDA ELF metadata access, selected by symbol rather than kernel-specific offsets."""
import struct
class Rejected(RuntimeError):pass
def require(ok,message):
 if not ok:raise Rejected(message)
class Image:
 def __init__(self,data,kernel):
  self.data=bytearray(data);self.kernel=kernel
  require(len(data)>=64,'Truncated ELF')
  h=struct.unpack_from('<16sHHIQQQIHHHHHH',data)
  require(h[0][:6]==b'\x7fELF\x02\x01' and h[2]==190,'Expected little-endian ELF64 CUDA image')
  require(h[11]==64 and h[12]>0 and h[6]+64*h[12]<=len(data),'Invalid ELF section table')
  self.abi=h[0][8];self.flags=h[7];self.table=[struct.unpack_from('<IIQQQQIIQQ',data,h[6]+64*i) for i in range(h[12])]
  st=self.table[h[13]];names=data[st[4]:st[4]+st[5]]
  self.names=[names[s[0]:].split(b'\0',1)[0].decode() for s in self.table];self.sections=dict(zip(self.names,self.table))
  require('.text.'+kernel in self.sections,'Selected kernel has no .text section')
  self.text_section=self.sections['.text.'+kernel];self.text_index=self.names.index('.text.'+kernel)
  sy=self.sections['.symtab'];require(sy[9]==24,'Unsupported ELF symbol layout');st=self.table[sy[6]];strings=data[st[4]:st[4]+st[5]];self.symbols=[]
  for i in range(sy[5]//24):
   x=struct.unpack_from('<IBBHQQ',data,sy[4]+i*24);name=strings[x[0]:].split(b'\0',1)[0].decode();self.symbols.append({'index':i,'name':name,'info':x[1],'section':x[3],'value':x[4],'size':x[5]})
  selected=[s for s in self.symbols if s['name']==kernel and s['section']==self.text_index];require(len(selected)==1,'Ambiguous kernel symbol');self.symbol=selected[0]
 def payload(self,name):s=self.sections[name];return bytes(self.data[s[4]:s[4]+s[5]])
 def text(self):return self.payload('.text.'+self.kernel)
 def word(self,pc):
  require(0<=pc and pc+16<=self.text_section[5] and pc%16==0,'Instruction outside selected .text')
  p=self.text_section[4]+pc;return int.from_bytes(self.data[p:p+16],'little')
 def set_word(self,pc,value):
  self.word(pc);p=self.text_section[4]+pc;self.data[p:p+16]=value.to_bytes(16,'little')
 def register_field(self):
  s=self.sections['.nv.info'];payload=self.payload('.nv.info');at=0;found=[]
  while at+4<=len(payload):
   fmt,kind,n=struct.unpack_from('<BBH',payload,at);size=n if fmt==4 else 0;require(at+4+size<=len(payload),'Truncated CUDA info attribute')
   if fmt==4 and kind==0x2f:
    require(size==8,'Unsupported EIATTR_REGCOUNT');symbol,count=struct.unpack_from('<II',payload,at+4)
    if symbol==self.symbol['index']:found.append((s[4]+at+8,count))
   at+=4+size
  require(len(found)==1,'Missing/ambiguous selected-kernel register count');return found[0]
 def registers(self):return self.register_field()[1]
 def set_registers(self,count):require(1<=count<=255,'Invalid register count');struct.pack_into('<I',self.data,self.register_field()[0],count)
 def nonempty_text_relocations(self):
  return [n for n,s in self.sections.items() if s[1] in (4,9) and s[7]==self.text_index and s[5]]
