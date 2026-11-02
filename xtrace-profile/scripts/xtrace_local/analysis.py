"""Conservative call-aware liveness overlay and role-cap analysis.

Upstream remains responsible for async ownership/hazards. This overlay only
adds exclusions; it never removes upstream live values or changes kernel code.
Recognized direct CUDA CALL.REL/RET calling conventions are analyzed from CFG.
Unresolved indirect control flow is rejected instead of guessed.
"""
from collections import defaultdict,deque
import re
from .elf import require,Rejected
CLASSES={'general':(0,255),'predicate':(256,7),'uniform_general':(264,63),'uniform_predicate':(328,7)}
def field(t,key,default=None):
 m=re.search(r'\b'+re.escape(key)+r'=(-?0x[0-9a-f]+)',t)
 if m:return int(m[1],16)
 if default is not None:return default
 raise Rejected('Missing operand '+key+': '+t)
def unconditional(t):return field(t,'Pg',7)==7 and field(t,'Pg@not',0)==0 and field(t,'UPg',7)==7 and field(t,'UPg@not',0)==0
def values(mask,kind):
 offset,n=CLASSES[kind];return [i for i in range(n) if mask&(1<<(offset+i))]
class Analysis:
 def __init__(self,kernel,entry_registers):
  kernel.parse_cfg();kernel.parse_register_liveness();self.kernel=kernel;self.entry_registers=entry_registers
  self.ins=list(kernel.list_instructions);self.text=[x.str(flatten=True).strip() for x in self.ins];self.n=len(self.ins);self.pcs=set(range(0,self.n*16,16));self.op=[t.split()[0] for t in self.text];self.constant_banks=sorted({int(m,16) for t in self.text for m in re.findall(r'_bank=(0x[0-9a-f]+)',t)})
  require(kernel.cfg.instruction_size==16,'Only SM90 instruction size is supported')
  for op in self.op:require(not op.startswith(('BRX','JMX','JMP','LEPC','RPCMOV','PRET')) and (not op.startswith('CALL') or op=='CALL.rel'),'Unsupported unresolved control flow: '+op)
  self.succ=[set() for _ in self.ins]
  # Preserve upstream branch/reconvergence CFG edges, then add direct calls/returns.
  for block in kernel.cfg.basic_blocks:
   if block.base_pc not in self.pcs:continue
   require(block.end_pc in self.pcs,'Malformed basic block')
   for pc in range(block.base_pc,block.end_pc,16):self.succ[pc//16].add(pc//16+1)
   for _,source,target in block.successors:
    if source in self.pcs and target in self.pcs:self.succ[source//16].add(target//16)
  # Native CFG can omit fallthrough for some predicated EXIT forms. Derive
  # direct branch/exit edges from the decoded guard operands explicitly.
  for i,t in enumerate(self.text):
   if self.op[i].startswith('BRA'):
    target=(i+1)*16+field(t,'sImm');require(target in self.pcs,'External direct branch target')
    self.succ[i]={target//16}|({i+1} if not unconditional(t) and i+1<self.n else set())
   elif self.op[i]=='PREEXIT':
    require(i+1<self.n,'PREEXIT without continuation');self.succ[i]={i+1}
   elif self.op[i].startswith('EXIT'):
    self.succ[i]={i+1} if not unconditional(t) and i+1<self.n else set()
  self.calls={};self.ret_bases={};self.allocation_guards={}
  for i,t in enumerate(self.text):
   if self.op[i]=='USETMAXREG' and 'UPu=' in t:
    require(unconditional(t) and i+3<self.n,'Unsupported predicated register allocation')
    predicate=field(t,'UPu');j=i+1;guard=self.text[j]
    if self.op[j].startswith('PLOP3'):
     copy=guard
     require(self.op[j]=='PLOP3.lut.2out.uniform' and unconditional(copy) and field(copy,'UPr')==predicate and field(copy,'UPr@not')==0 and field(copy,'Pp')==7 and field(copy,'Pq')==7 and field(copy,'uimm8')==0x80 and field(copy,'vimm8')==0,'Unknown allocation predicate conversion')
     predicate=field(copy,'Pu');j+=1;guard=self.text[j]
     require(field(guard,'Pg')==predicate and field(guard,'Pg@not')==1,'Unknown allocation success guard')
    else:require(field(guard,'UPg')==predicate and field(guard,'UPg@not')==1,'Unknown uniform allocation guard')
    require(self.op[j].startswith('BRA'),'Missing allocation retry branch');target=(j+1)*16+field(guard,'sImm')
    require(target==i*16 or (target==(i-1)*16 and self.op[i-1].startswith('WARPSYNC')),'Unknown allocation retry target')
    self.allocation_guards[j]={'allocation':i,'new_cap':field(t,'Sb'),'failure':target//16,'success':j+1}
  for i,t in enumerate(self.text):
   if self.op[i]=='CALL.rel':
    target=(i+1)*16+field(t,'Sa');require(target in self.pcs,'External/unresolved CALL target');require(i+1<self.n,'CALL has no continuation');self.calls[i]=target//16;self.succ[i]={i+1}
   elif self.op[i]=='RET':
    base=(i+1)*16+field(t,'Ra_offset');require(base in self.pcs,'RET base is outside selected .text');self.ret_bases[i]=base;self.succ[i]=set()
  self.callees={};self.ret_to_continuations=defaultdict(set)
  for target in sorted(set(self.calls.values())):
   seen=set();queue=[target];returns=set()
   while queue:
    i=queue.pop()
    if i in seen:continue
    seen.add(i)
    if self.op[i]=='RET':returns.add(i);continue
    require(self.op[i]!='USETMAXREG','Device function changes register budget; not supported')
    queue.extend(self.succ[i]-seen)
   require(returns,'CALL target has no resolved RET')
   bases={self.ret_bases[i] for i in returns};require(len(bases)==1,'Ambiguous return bases in callee')
   self.callees[target]={'body':seen,'returns':returns,'base':next(iter(bases))}
  self.call_graph={t:{self.calls[i] for i in x['body'] if i in self.calls} for t,x in self.callees.items()}
  def visit(t,active,done):
   require(t not in active,'Recursive calls require a different ABI analysis')
   if t in done:return
   for child in self.call_graph[t]:visit(child,active|{t},done)
   done.add(t)
  done=set()
  for t in self.call_graph:visit(t,set(),done)
  for call,target in self.calls.items():
   for ret in self.callees[target]['returns']:self.ret_to_continuations[ret].add(call+1)
  self.extended=[set(x) for x in self.succ]
  for call,target in self.calls.items():self.extended[call]={target}|({call+1} if not unconditional(self.text[call]) else set())
  for ret,continuations in self.ret_to_continuations.items():self.extended[ret]|=continuations
  self.uses=[0]*self.n;self.defs=[0]*self.n;self.accesses={kind:set() for kind in CLASSES};self.written=[set() for _ in self.ins]
  for kind,regs in kernel.get_register_op_traces().items():
   if kind not in CLASSES:continue
   offset,count=CLASSES[kind]
   for reg,events in regs.items():
    if not 0<=reg<count:continue
    self.accesses[kind].add(reg);bit=1<<(offset+reg)
    for pc,access in events:
     require(pc in self.pcs,'Register trace has unknown PC');i=pc//16
     if 'r' in access:self.uses[i]|=bit
     if 'w' in access:
      self.written[i].add((kind,reg))
      if unconditional(self.text[i]):self.defs[i]|=bit
  self.live=[0]*self.n;pred=[set() for _ in self.ins]
  for i,edges in enumerate(self.extended):
   for j in edges:pred[j].add(i)
  work=deque(range(self.n-1,-1,-1));queued=set(work)
  while work:
   i=work.popleft();queued.discard(i);out=0
   for j in self.extended[i]:out|=self.live[j]
   new=self.uses[i]|(out&~self.defs[i])
   if new!=self.live[i]:
    self.live[i]=new
    for p in pred[i]:
     if p not in queued:work.append(p);queued.add(p)
  # A callee cannot alter the cap (checked above), so caller continuations keep
  # their cap; callees inherit the union of the caps at their call sites.
  self.caps=[set() for _ in self.ins];self.caps[0]={entry_registers};work=deque([0]);queued={0}
  while work:
   i=work.popleft();queued.discard(i);out=self.caps[i]
   if self.op[i]=='USETMAXREG':out={field(self.text[i],'Sb')}|(out if 'UPu=' in self.text[i] or not unconditional(self.text[i]) else set())
   edges=self.succ[i]|({self.calls[i]} if i in self.calls else set())
   for j in edges:
    propagated=out
    if i in self.allocation_guards:
     g=self.allocation_guards[i];require(j in (g['failure'],g['success']),'Unexpected allocation-guard edge')
     propagated=self.caps[g['allocation']] if j==g['failure'] else {g['new_cap']}
    update=propagated-self.caps[j]
    if update:
     self.caps[j]|=update
     if j not in queued:work.append(j);queued.add(j)
  # Recognize software return-address definitions on a unique predecessor chain.
  pred_simple=[set() for _ in self.ins]
  for i,edges in enumerate(self.succ):
   for j in edges:pred_simple[j].add(i)
  self.return_literals={}
  for call,target in self.calls.items():
   base=self.callees[target]['base'];wanted=(call+1)*16-base;node=call;seen=set();writes=set();found=[]
   while len(pred_simple[node])==1:
    j=next(iter(pred_simple[node]))
    if j in seen or j in self.calls:break
    seen.add(j);t=self.text[j]
    if self.op[j]=='MOV' and 'Sb=' in t and field(t,'Sb')==wanted and unconditional(t):
     reg=field(t,'Rd')
     if ('general',reg) not in writes:found.append((j,reg))
    writes|=self.written[j];node=j
   require(len(found)==1,'Unrecognized or ambiguous return-address definition at PC '+hex(call*16))
   j,reg=found[0];require(bool(self.live[target]&(1<<reg)),'Return-address register is not consumed by callee')
   self.return_literals[call]={'index':j,'register':reg,'base':base,'value':wanted}
 def site_analysis(self,init,sites,explicit):
  for i in [init,*sites]:require(0<=i<self.n and self.caps[i],'Unreachable probe/init index '+str(i))
  # INIT resets the cursor: a loop/repeated-call INIT would overwrite history.
  seen_after=set();pending=list(self.extended[init])
  while pending:
   i=pending.pop();require(i!=init,'INIT can execute repeatedly; choose a dominating noncyclic initialization point')
   if i in seen_after:continue
   seen_after.add(i);pending.extend(self.extended[i]-seen_after)
  # Cutting INIT must make every selected point unreachable from entry.
  seen=set();work=[0]
  while work:
   i=work.pop()
   if i==init or i in seen:continue
   seen.add(i);work.extend(self.extended[i]-seen)
  require(not (set(sites)-{init})&seen,'INIT does not dominate every selected site')
  extras={kind:set(explicit.get(kind,[])) for kind in CLASSES};details=[]
  for i in [init,*sites]:
   row={'index':i,'caps':sorted(self.caps[i]),'extra_live':{}}
   for kind in CLASSES:
    native=set(self.kernel._gw_instance.get_live_registers_at_pc(i*16,kind));extra=set(values(self.live[i],kind))-native;extras[kind]|=extra;row['extra_live'][kind]=sorted(extra)
   details.append(row)
  # Persistent-state selection separately excludes all original UR accesses;
  # scratch URs only need the site/call-aware semantic exclusions above.
  return {k:sorted(v) for k,v in extras.items()},details
 def summary(self):
  return {'instructions':self.n,'calls':len(self.calls),'returns':len(self.ret_bases),'callee_entries':sorted(i*16 for i in self.callees),'return_literals':{str(i*16):x for i,x in self.return_literals.items()},'preexit_fallthrough_pcs':[i*16 for i,op in enumerate(self.op) if op=='PREEXIT'],'allocation_retry_guards':self.allocation_guards,'call_aware_liveness':True,'scope':'Conservative context-insensitive call/return overlay, unioned with upstream async-aware liveness; unresolved control flow and recursive ABI rejected.'}
