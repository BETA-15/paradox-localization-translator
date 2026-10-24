#!/bin/zsh
# Take the 4 screenshots in every site language from a given commit/tag of the app.
# Usage: run_all.sh <repo> <commit-or-tag> <out_dir> [page codes...]
# Each language runs in a fresh throwaway HOME / data root with the made-up sample mod.
set -u
REPO=$1; REF=$2; OUT=$3; shift 3
HERE=${0:A:h}
PY=$REPO/.venv-build/bin/python          # has tkinterdnd2
D=/Users/Shared/PLT_Demo
typeset -A UI TGT
UI=(en english ja japanese fr french de german es spanish ko korean pl polish pt-BR braz_por ru russian zh-Hans simp_chinese tr turkish)
TGT=(en french ja japanese fr french de german es spanish ko korean pl polish pt-BR braz_por ru russian zh-Hans simp_chinese tr turkish)
CODES=(${@:-en ja fr de es ko pl pt-BR ru zh-Hans tr})
swiftc -O $HERE/win.swift -o $HERE/win || exit 1
for c in $CODES; do
  rm -rf $D; mkdir -p $D/src $D/data $OUT/raw/$c
  python3 $HERE/make_sample.py $D ${TGT[$c]}
  git -C $REPO archive $REF app | tar -x -C $D/src
  ( cd $D && HOME=$D PARADOX_TRANSLATOR_DATA_ROOT=$D/data SHOT_UI_LANG=${UI[$c]} SHOT_TARGET=${TGT[$c]} \
      $PY -I $HERE/shoot.py $D/src/app $OUT/raw/$c > $OUT/raw/$c.log 2>&1 & echo $! > $OUT/raw/$c.pid )
  sleep 50; kill $(cat $OUT/raw/$c.pid) 2>/dev/null; sleep 2
  echo "$c: $(ls $OUT/raw/$c | tr '\n' ' ')"
done
rm -rf $D $HERE/win $HERE/__pycache__
