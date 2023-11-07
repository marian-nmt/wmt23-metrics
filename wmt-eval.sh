#!/usr/bin/env bash
set -eux
    

devices="0 1 2 3 4 5" # run on GPUs
tests="wmt23 wmt22"
tests="wmt23"   # wmt23 only
metrics=(chrfoid-wmt23 $(echo cometoid22-wmt{22,23,21}))

# score
for testname in $tests; do
    data_file=$(python -m evaluate -t $testname flatten --no-ref)
    n_segs=$(wc -l < $data_file)
    for m in ${metrics[@]}; do
        out=${data_file%.tsv}.seg.score.$m;
        [[ -f $out._OK ]] && continue;
        rm -f $out; `# remove incomplete file, if any`
        cut -f4,6 $data_file \
            | pymarian-evaluate --stdin -d $devices -m $m \
            | tqdm --desc=$m --total=$n_segs > $out \
            && touch $out._OK;
    done
done


# evaluate
for testname in $tests; do
    data_file=$(python -m evaluate -t $testname flatten --no-ref)
    for m in ${metrics[@]}; do
        score_file=${data_file%.tsv}.seg.score.$m;
        [[ -f $score_file._OK ]] || { echo "Error: $scores_file._OK  not found"; continue;}
        # adding "-redo" to name to avoid conflicts with the submitted results alreqady exists in the package
        python -m evaluate -t $testname full --no-ref --name $m-redo --scores $score_file;
    done
done


