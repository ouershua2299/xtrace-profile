"""Reusable CPU-only Xtrace adapter; no model/kernel allowlist, no GPU launch."""
import hashlib,importlib.metadata,json,math,re,tempfile,threading,time
from pathlib import Path
from .elf import Image,require,Rejected
from .analysis import Analysis,CLASSES
from .emission import repair,audit
LOCK=threading.RLock()
NATIVE_SHA='c19c621b83404861acb55ac455c58c6afa206f4ec2d6b2a8cebda4f024788dfe'
def sha(x):return hashlib.sha256(x).hexdigest()
def dims(x):require(isinstance(x,list) and len(x)==3 and all(type(v)is int and v>0 for v in x),'Expected three positive launch dimensions');return tuple(x)
def splice(cubin_path,config_path,output):
 start=time.monotonic();source_hashes={p.name:sha(p.read_bytes()) for p in Path(__file__).parent.glob('*.py')};cubin_path=Path(cubin_path);config_path=Path(config_path);output=Path(output);proof_path=output.with_suffix('.json');raw_path=output.with_name(output.stem+'.upstream-unvalidated.cubin')
 require(output.suffix=='.cubin' and all(not p.exists() for p in [output,proof_path,raw_path]),'Use fresh output/proof paths')
 config=json.loads(config_path.read_text());require(isinstance(config,dict) and not set(config)-{'original_sha256','kernel_name_pattern','arch','grid','block','records','sites','init_insert_index','init_scope','excluded_registers','schedule','expected_by_warp','notes'},'Unknown configuration field; filters are not inferred');original_bytes=cubin_path.read_bytes();require(sha(original_bytes)==config.get('original_sha256'),'Input SHA does not match the selected sites')
 require(importlib.metadata.version('gwatch')=='0.0.35','Inspect a different gwatch version before enabling this compatibility backend')
 from gwatch.cuda.binary import Cubin
 from gwatch.cuda.xtrace._schema import SassTraceSite,TraceSchema_SASS
 import gwatch.cuda.xtrace._sass_instrumenter as upstream
 import gwatch
 native=Path(gwatch.__file__).parent/'libgwatch_dark_cuda128_x86_64.so';require(native.is_file() and sha(native.read_bytes())==NATIVE_SHA,'Unrecognized native library')
 image=Cubin();image.fill(str(cubin_path));image.parse();pattern=re.compile(config['kernel_name_pattern']);names=[n for n in image.get_map_kernel_def() if pattern.search(n)];require(len(names)==1,'Select exactly one kernel entry');name=names[0];kernel=image.get_kerneldef_by_name(name)
 requested=str(config.get('arch','')).lower().removeprefix('sm_');actual=str(kernel.params.arch_version).removeprefix('sm_');require(requested in ('90','90a') and actual in ('90','90a'),'Local relocation backend supports SM90/SM90a only; other architectures are not silently patched')
 elf=Image(original_bytes,name);require(elf.abi==8,'CUDA ELF ABI8 is the validated format');require(((elf.flags>>8)&255)==90,'ELF architecture differs from SM90')
 original_params=sorted(zip(kernel.list_param_offsets_reversed,kernel.list_param_sizes_reversed));original_offsets=[x[0] for x in original_params];original_sizes=[x[1] for x in original_params]
 entry_regs=elf.registers();require(entry_regs==int(kernel.params.num_registers),'Input register metadata disagrees with parser');analysis=Analysis(kernel,entry_regs)
 grid,block=dims(config['grid']),dims(config['block']);require(math.prod(block)%32==0 and math.prod(block)<=1024,'Warp mode requires complete warps')
 budget=config['records'];require(type(budget)is int and budget>1,'Need a positive record budget with headroom');init=config.get('init_insert_index',1);require(type(init)is int and 1<=init<analysis.n,'Invalid INIT location')
 descriptions=config['sites'];require(isinstance(descriptions,list) and 1<=len(descriptions)<=63,'Need 1..63 sites');sites=[];indices=[]
 allowed={'insert_index','label','warp_level','value_reg','value_width_bits','value_is_uniform','value_is_smid'}
 for s in descriptions:
  require(isinstance(s,dict) and not set(s)-allowed,'Unknown site field; runtime filters are not supported');i=s['insert_index'];require(type(i)is int and init<=i<analysis.n and i not in indices,'Invalid/duplicate site index')
  require(s.get('warp_level',True) is True and s.get('value_width_bits',32)==32 and not s.get('value_is_uniform',False) and not s.get('value_is_smid',False),'Unsupported trace layout')
  value=s.get('value_reg',255);require(type(value)is int and 0<=value<=255,'Invalid physical payload register');sites.append(SassTraceSite(insert_index=i,warp_level=True,value_reg=value,value_width_bits=32));indices.append(i)
 explicit=config.get('excluded_registers',{});require(not set(explicit)-set(CLASSES),'Unknown register class')
 for kind,regs in explicit.items():require(isinstance(regs,list) and all(type(v)is int and 0<=v<CLASSES[kind][1] for v in regs),'Invalid excluded-register list')
 exclusions,site_details=analysis.site_analysis(init,indices,explicit)
 schema=TraceSchema_SASS(sites,grid,block,'sm',per_thread_records=budget);schedule=config.get('schedule','first_feasible');require(schedule in ('first_feasible','least_makespan'),'Unsupported schedule')
 class Protected(upstream.TraceInstrumenter_SASS):
  def _instrument_warp(self,kd,*args,**kwargs):
   for kind,regs in exclusions.items():kd._gw_instance.exclude_instrument_registers(kind,regs)
   return super()._instrument_warp(kd,*args,**kwargs)
  def _allocate_trace_pointer(self,kd,live_pcs):
   # Exclusions are additive in 0.0.35. Use a separate planning definition so
   # globally used URs are unavailable to persistent state, without forbidding
   # those registers as short-lived scratch at a site where they are dead.
   planner=Cubin();planner.fill(str(cubin_path));planner.parse();pk=planner.get_kerneldef_by_name(name);pk.parse_cfg();pk.parse_register_liveness()
   pk._gw_instance.exclude_instrument_registers('uniform_general',sorted(analysis.accesses['uniform_general']|set(exclusions['uniform_general'])))
   pair=pk.collect_allocatable_register_pairs('uniform_general',list(range(0,analysis.n*16,16)),2)
   require(not set(pair)&analysis.accesses['uniform_general'],'Persistent trace state overlaps original UR usage')
   kd._gw_instance.exclude_instrument_registers('uniform_general',list(pair))
   self.local_persistent_urs=list(pair);return 'uniform_general',pair
 cloned=image.clone();tracer=Protected(name,cloned.get_kerneldef_by_name(name),cloned,None,schema,clock_type='sm',splice_mode='plain',schedule_mode=int(schedule=='least_makespan'))
 with LOCK:
  saved=upstream._INIT_INSERT_INDEX;upstream._INIT_INSERT_INDEX=init
  try:tracer.instrument()
  finally:upstream._INIT_INSERT_INDEX=saved
 emitted=Cubin();emitted.add_kerneldef(tracer.kernel_def_sass);raw_bytes=emitted.serialize();output.parent.mkdir(parents=True,exist_ok=True)
 # Keep upstream output distinctly labeled, including when later validation rejects it.
 with raw_path.open('xb') as f:f.write(raw_bytes)
 raw_image=Cubin();raw_image.fill(str(raw_path));raw_image.parse();raw_kernel=raw_image.get_kerneldef_by_name(name);raw_kernel.parse_cfg()
 repaired,emission,mapping,starts=repair(original_bytes,raw_bytes,name,analysis,raw_kernel,tracer.map_site_probe_pcs,init,indices)
 with tempfile.NamedTemporaryFile(dir=output.parent,suffix='.cubin',delete=False) as tmp:tmp.write(repaired);temp_path=Path(tmp.name)
 try:
  fixed_image=Cubin();fixed_image.fill(str(temp_path));fixed_image.parse();fixed_kernel=fixed_image.get_kerneldef_by_name(name);fixed_kernel.parse_cfg();binary_audit=audit(original_bytes,repaired,name,analysis,fixed_kernel,emission,starts)
  uniform_writes={}
  for reg,events in fixed_kernel.get_register_op_traces().get('uniform_general',{}).items():
   if reg==63:continue
   for pc,access in events:
    if 'w' in access:uniform_writes.setdefault(pc,set()).add(reg)
  for site,pcs in tracer.map_site_probe_pcs.items():
   if int(site)>=0:
    changed=set().union(*(uniform_writes.get(pc,set()) for pc in pcs))
    require(changed<=set(tracer.local_persistent_urs[2:]),'A RECORD clobbers persistent state or unmodeled uniform scratch')
  cap_checks=[]
  for site,pcs in tracer.map_site_probe_pcs.items():
   original_index=init if int(site)<0 else indices[int(site)];caps=analysis.caps[original_index];used=[]
   for pc in pcs:used.extend(int(op.value) for op in fixed_kernel.list_instructions[pc//16].map_register_operands.get('general',[]) if int(op.value)!=255)
   require(max(used,default=-1)<min(caps),'Probe exceeds original role cap; refusing to lower metadata over live registers')
   cap_checks.append({'site':site,'index':original_index,'caps':sorted(caps),'max_probe_gpr':max(used,default=-1),'pass':True})
  fixed_params=sorted(zip(fixed_kernel.list_param_offsets_reversed,fixed_kernel.list_param_sizes_reversed));fixed_offsets=[x[0] for x in fixed_params];fixed_sizes=[x[1] for x in fixed_params]
  require(fixed_sizes[:-1]==original_sizes and fixed_sizes[-1]==8 and fixed_offsets[:-1]==original_offsets,'Original parameter ABI changed')
  require(fixed_offsets[-1]>=max((off+size for off,size in zip(original_offsets,original_sizes)),default=0) and fixed_offsets[-1]%8==0,'Invalid appended trace pointer ABI')
  require(source_hashes=={p.name:sha(p.read_bytes()) for p in Path(__file__).parent.glob('*.py')},'Adapter source changed during generation')
  proof={'adapter_source_sha256':source_hashes,'constant_banks_checked':emission['constant_banks_checked'],'status':'static_verified_runtime_validation_required','backend':'local-sm90-compat-v1','package':'gwatch','version':'0.0.35','native_sha256':NATIVE_SHA,'native_modified':False,'kernel':name,'arch':actual,'requested_arch':requested,'original_sha256':sha(original_bytes),'instrumented_sha256':sha(repaired),'upstream_unvalidated_sha256':sha(raw_bytes),'source_cubin':str(cubin_path.resolve()),'config':config,'clock':'sm','schedule':schedule,'splice_mode':'plain','original_registers':entry_regs,'instrumented_registers':entry_regs,'emitted_registers_before_repair':emission['emitted_registers'],'probe_pcs':tracer.map_site_probe_pcs,'site_reports':tracer.map_site_reports,'binary_audit':binary_audit,'relocation_changes':emission['changes'],'pc_map':mapping,'register_gate':cap_checks,'parameter_abi':{'original_sizes':original_sizes,'original_offsets':original_offsets,'traced_sizes':fixed_sizes,'traced_offsets':fixed_offsets},'liveness':analysis.summary(),'site_analysis':site_details,'effective_exclusions':exclusions,'persistent_uniform_registers':tracer.local_persistent_urs,'static_seconds':time.monotonic()-start,'schema':{'grid':list(grid),'block':list(block),'records':budget,'slab_bytes':schema.warp_slab_bytes,'header_bytes':schema.warp_header_bytes,'record_bytes':schema.warp_record_bytes,'total_bytes':schema.total_bytes,'timestamp_bits':26,'site_id_bits':schema.warp_site_id_bits,'site_count':len(sites),'clock':'sm','zero_payload':all(s.get('value_reg',255)==255 for s in descriptions)},'limitations':['SM90 backend and recognized direct-call ABI only; unsupported control flow rejected','Conservative interprocedural overlay adds exclusions to upstream async-aware analysis; may reject high-pressure sites','Static success does not prove output correctness, event coverage or low perturbation for a new workload']}
  with output.open('xb') as f:f.write(repaired)
  with proof_path.open('x') as f:f.write(json.dumps(proof,indent=2,default=str)+'\n')
  return proof
 finally:temp_path.unlink(missing_ok=True)
