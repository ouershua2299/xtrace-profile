import argparse,json
from pathlib import Path
from . import splice,Rejected
p=argparse.ArgumentParser(description='Local generic SM90 Xtrace: original probes plus audited compatibility checks. CPU only.')
p.add_argument('--cubin',type=Path,required=True);p.add_argument('--config',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
try:
 r=splice(a.cubin,a.config,a.output);print(json.dumps({k:r[k] for k in ['status','kernel','original_registers','emitted_registers_before_repair','binary_audit','schema']},indent=2))
except (Rejected,ValueError,RuntimeError,KeyError,TypeError,OSError) as e:p.exit(2,'Local Xtrace rejected: '+str(e)+'\n')
