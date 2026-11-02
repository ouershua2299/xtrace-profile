#!/usr/bin/env python3
"""Stable entrypoint for the local kernel-generic Xtrace compatibility adapter."""
import argparse,json
from pathlib import Path
from xtrace_local import splice,Rejected

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--cubin',type=Path,required=True);p.add_argument('--config',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 try:
  proof=splice(a.cubin,a.config,a.output)
  print(json.dumps({k:proof[k] for k in ['status','backend','kernel','original_registers','emitted_registers_before_repair','binary_audit','schema']},indent=2))
 except (Rejected,ValueError,RuntimeError,OSError,KeyError,TypeError,ImportError) as e:p.exit(2,'Local Xtrace rejected: '+str(e)+'\n')
if __name__=='__main__':main()
