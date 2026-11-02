"""SM90 emission compatibility: original budget and complete direct-call relocation."""
import re
from .elf import Image,require
from .analysis import field
REL_MASK=(255<<16)|(((1<<48)-1)<<34)
CONTROL_MASK=((1<<23)-1)<<105
MOV_MASK=0xffffffff<<32
def decode_rel(w):
 x=((w>>16)&255)|(((w>>34)&((1<<48)-1))<<8)
 return (x-(1<<56) if x&(1<<55) else x)*4
def encode_rel(w,disp):
 require(disp%4==0 and -(1<<57)<=disp<(1<<57),'Unencodable SM90 relative address')
 x=(disp//4)&((1<<56)-1);v=(w&~REL_MASK)|((x&255)<<16)|((x>>8)<<34);require(decode_rel(v)==disp,'Relative address encoding check');return v
def normalized(t):return re.sub(r'\b(?:sImm|Sa|Ra_offset)=-?0x[0-9a-f]+','ADDR',t)
def layout(analysis,emitted_kernel,probe_pcs):
 added={pc for v in probe_pcs.values() for pc in v};new=list(emitted_kernel.list_instructions);kept=[(i*16,x) for i,x in enumerate(new) if i*16 not in added]
 require(len(kept)>=analysis.n and all(x.str(flatten=True).startswith('NOP') for _,x in kept[analysis.n:]),'Unexpected emitted instruction count')
 for i,(_,ins) in enumerate(kept[:analysis.n]):require(normalized(analysis.text[i])==normalized(ins.str(flatten=True).strip()),'Original operation/order changed at '+hex(i*16))
 return {i*16:pc for i,(pc,_) in enumerate(kept[:analysis.n])},added

def repair(original_bytes,emitted_bytes,name,analysis,emitted_kernel,probe_pcs,init,sites):
 original=Image(original_bytes,name);image=Image(emitted_bytes,name);mapping,added=layout(analysis,emitted_kernel,probe_pcs)
 require(not original.nonempty_text_relocations(),'Unresolved link-time relocations require a separate backend')
 for bank in analysis.constant_banks:
  candidates=[n for n in (f'.nv.constant{bank}.'+name,f'.nv.constant{bank}') if n in original.sections]
  require(len(candidates)==1,'Unresolved referenced constant bank '+str(bank))
  section=candidates[0];require(section in image.sections,'Emitter dropped referenced constant bank '+section)
  before=original.payload(section);after=image.payload(section)
  require(after[:len(before)]==before if bank==0 else after==before,'Emitter changed referenced constant data '+section)
 starts={init*16:min(probe_pcs[-1])}
 for i,site in enumerate(sites):starts[site*16]=min(starts.get(site*16,1<<60),min(probe_pcs[i]))
 entry=lambda pc:starts.get(pc,mapping[pc])
 changes=[];return_moves={}
 def change(pc,new,kind,detail):
  before=image.word(pc)
  if before!=new:image.set_word(pc,new);changes.append({'kind':kind,'new_pc':pc,'before':before.to_bytes(16,'little').hex(),'after':new.to_bytes(16,'little').hex(),**detail})
 for call,target in analysis.calls.items():
  pc=call*16;npc=mapping[pc];old_disp=field(analysis.text[call],'Sa');require(decode_rel(original.word(pc))==old_disp,'CALL encoding differs from SM90 definition')
  dest=entry(target*16);change(npc,encode_rel(image.word(npc),dest-npc-16),'call_target',{'old_pc':pc,'target':dest})
  info=analysis.return_literals[call];mp=info['index']*16;newmp=mapping[mp];old_value=info['value'];new_value=entry((call+1)*16)-mapping[info['base']]
  require(0<=new_value<2**32 and (original.word(mp)>>32)&0xffffffff==old_value,'Unsupported return literal encoding')
  if mp in return_moves:require(return_moves[mp]==new_value,'Conflicting shared return literal')
  return_moves[mp]=new_value;change(newmp,(image.word(newmp)&~MOV_MASK)|(new_value<<32),'return_literal',{'old_pc':mp,'value':new_value})
 for i,base in analysis.ret_bases.items():
  pc=i*16;npc=mapping[pc];require(decode_rel(original.word(pc))==field(analysis.text[i],'Ra_offset'),'RET encoding differs from SM90 definition')
  change(npc,encode_rel(image.word(npc),mapping[base]-npc-16),'return_base',{'old_pc':pc,'base':mapping[base]})
 # Restore only the input symbol's original entry budget. Probe allocation must
 # independently fit the role-specific caps before this image is accepted.
 before=image.registers();image.set_registers(original.registers())
 require(all(image.word(pc)==Image(emitted_bytes,name).word(pc) for pc in added),'A repair changed an upstream probe')
 return bytes(image.data),{'original_registers':original.registers(),'emitted_registers':before,'registers':image.registers(),'changes':changes,'pc_map':mapping,'return_moves':return_moves,'probe_instruction_count':len(added),'constant_banks_checked':analysis.constant_banks},mapping,starts

def audit(original_bytes,repaired_bytes,name,analysis,fixed_kernel,proof,starts):
 original=Image(original_bytes,name);fixed=Image(repaired_bytes,name);mapping=proof['pc_map'];new=list(fixed_kernel.list_instructions);identical=0;control_only=0;branches=0;site_skip_edges=[]
 require(fixed.registers()==analysis.entry_registers==int(fixed_kernel.params.num_registers),'Register declaration mismatch after serialization')
 for i,at in enumerate(analysis.text):
  pc=i*16;npc=mapping[pc];bt=new[npc//16].str(flatten=True).strip();op=analysis.op[i];a=original.word(pc);b=fixed.word(npc)
  if a==b:identical+=1
  if op.startswith(('BRA','BSSY')):
   key='sImm' if 'sImm=' in at else 'Sa';dest=pc+16+field(at,key);ndest=npc+16+field(bt,key)
   require(dest in mapping and ndest in {mapping[dest],starts.get(dest,mapping[dest])},'Branch target was not preserved')
   require(normalized(at)==normalized(bt),'Branch operands changed');branches+=1
   if dest in starts and ndest!=starts[dest]:site_skip_edges.append({'original_source':pc,'original_target':dest,'new_target':ndest,'probe_head':starts[dest]})
  elif op=='CALL.rel':
   dest=analysis.calls[i]*16;require(npc+16+field(bt,'Sa')==starts.get(dest,mapping[dest]),'CALL target mismatch')
   require(normalized(at)==normalized(bt) and not ((a^b)&~(REL_MASK|CONTROL_MASK)),'CALL changed nonrelocation bits');branches+=1
  elif op=='RET':
   require(npc+16+field(bt,'Ra_offset')==mapping[analysis.ret_bases[i]],'RET base mismatch')
   require(normalized(at)==normalized(bt) and not ((a^b)&~(REL_MASK|CONTROL_MASK)),'RET changed nonrelocation bits')
  elif pc in proof['return_moves']:
   require(field(bt,'Sb')==proof['return_moves'][pc],'Return MOV mismatch')
   require(re.sub(r'Sb=0x[0-9a-f]+','RETURN',at)==re.sub(r'Sb=0x[0-9a-f]+','RETURN',bt) and not ((a^b)&~(MOV_MASK|CONTROL_MASK)),'Return MOV changed unrelated bits')
  else:
   require(at==bt and not ((a^b)&~CONTROL_MASK),'Original semantic bits changed at '+hex(pc))
   if a!=b:control_only+=1
 # Missing a record at a branch-entry site must not be silently accepted.
 require(not site_skip_edges,'An upstream branch skips a selected probe; choose another site or fix that backend explicitly: '+str(site_skip_edges[:3]))
 return {'original_instructions':analysis.n,'bit_identical':identical,'nonrelocation_control_only':control_only,'direct_targets_checked':branches,'call_targets_checked':len(analysis.calls),'return_literals_checked':len(analysis.return_literals),'return_bases_checked':len(analysis.ret_bases),'all_probe_bytes_preserved':True}
