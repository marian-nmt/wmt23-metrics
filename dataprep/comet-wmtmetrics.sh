#!/usr/bin/env bash

set -eu
MYDIR="$(realpath "$(dirname "${BASH_SOURCE[0]}")" )"
SCRIPTS="$(realpath "$MYDIR/../..")"


# this directory was prepared for mt-detect work

NGPUS=8
BATCH_SIZE=32
MODEL_ID=Unbabel/wmt22-comet-da
MODEL_NAME=$(basename $MODEL_ID)
export NCCL_DEBUG=WARN

DATA_DIR=/mnt/tg/projects/mt-metrics/2023-metric-distill/data/wmt-metrics/merged

log() {
  echo -e "[$(date -Is)]{L$BASH_LINENO}:: $@" >&2
}

export PATH=$PATH:$HOME/.local/bin


get_comet_scores() {
    # NOTE: I tried running on 8 GPUs but it produced NCCL logs into STDOUT
    #  I couldnt parse seg scores from it. So, I abandoned this function
    # and instead use gnu parallel to run

    local src ref hyp
    local model=$MODEL_ID
    # parse --src <file> --ref <file> --hyp <file> --model <model>
    #
    while [[ $# -gt 0 ]]; do
        case $1 in
            --src) src=$2; shift 2;;
            --ref) ref=$2; shift 2;;
            --hyp) hyp=$2; shift 2;;
            --model) model=$2; shift 2;;
            *) echo "Unknown option $1"; exit 1;;
        esac
    done
    [[ -f $src && -f $ref && -f $hyp ]] || {
        log "Missing one or more files: $src $ref $hyp"; exit 1;
    }
    log "src ref hyp :: $src $ref $hyp"
    cmd="comet-score --quiet --gpus $NGPUS --batch_size $BATCH_SIZE --model $model -s $src -t $hyp -r $ref"
    log "Run:: $cmd"
    $cmd
}
export -f get_comet_scores


score-all(){
    comet-score --help > /dev/null || {
        log "Installing unbabel-comet"
        pip install --upgrade pip >&2
        pip install unbabel-comet >&2
    }
    which tqdm > /dev/null || {
        log "Installing tqdm"
        pip install tqdm >&2
    }

    for inp in  $DATA_DIR/{wmt_sans22.shuf.{dev,train},wmt22}.tsv; do
        out=${inp%.tsv}.$MODEL_NAME.score
        [[ -f $out && -f $out._OK ]] && { echo "Skip $out"; continue; }
        log "Processing $inp -> $out"
        rm -f $out $out._OK
        #tmp=$(mktemp)
        tmp=tmp.$(basename $inp .tsv)   #for debugging
        rm -f $tmp.*
        cut -f5 $inp > $tmp.src
        cut -f6 $inp > $tmp.ref
        cut -f7 $inp > $tmp.hyp
        #trap "rm -f $tmp.src $tmp.ref $tmp.hyp" EXIT
        get_comet_scores --src $tmp.src --ref $tmp.ref --hyp $tmp.hyp \
            | grep '\t Segment ' \
            | awk -F '[:\t]' 'NF==4{print $NF}' \
            | tqdm > $out && touch $out._OK
    done
}


format-refless(){
    for inp in $DATA_DIR/{wmt_sans22.shuf.{dev,train},wmt22}.tsv; do
        score=${inp%.tsv}.$MODEL_NAME.score
        out=${inp%.tsv}.$MODEL_NAME.refless.tsv
        [[ -f $inp && -f $inp._OK && -f $score && -f $score._OK ]] && { log "ERROR: $inp or $score is invalid"; continue; }
        [[ -f $out && -f $out._OK ]] && { log "Skip $out"; continue; }

        # check line count
        [[ $(wc -l < $inp ) -eq $(wc -l < $score ) ]] || {
            log "ERROR: $inp and $score have different line counts"
            continue
        }
        log "Processing $inp $score -> $out"
        rm -f $out $out._OK

        # input: 1=year 2=langs 3=docid 4=sysname 5=src 6=ref 7=hyp 8=score
        # output: 1=langs 2=docid 3=system 4=score 5=src 6=tgt
        paste $inp $score | awk -F '\t' -v OFS='\t' '{print $1"|"$2, $3, $4, $8, $5, $7}' > $out && touch $out._OK
        log "Done $out"
    done
}

spm-length(){
    spm_model=~/.cache/marian/metrics/comet20-da-src+ref/roberta.vocab.spm
    [[ -f $spm_model ]] || {
        log "ERROR: $spm_model not found"
        exit 1
    }
    for inp in  $DATA_DIR/{wmt_sans22.shuf.{dev,train},wmt22}.tsv; do
        out=${inp%.tsv}.roberta_spm.len
        [[ -f $out && -f $out._OK ]] && { echo "Skip $out"; continue; }
        cut -f5,6,7 $inp \
            | tr '\t' '\n' \
            | spm_encode --model  $spm_model \
            | awk '{printf "%d%s", NF, NR % 3 == 0 ? "\n" : "\t"}' > $out && touch $out._OK
    done
}

clean-refless(){
    # remove rows having empty columns
    for inp in  $DATA_DIR/{wmt_sans22.shuf.{dev,train},wmt22}.*.refless*.tsv; do
        out=${inp%.tsv}.clean.tsv
        [[ -f $out && -f $out._OK ]] && { echo "Skip $out"; continue; }
        awk -F '\t' -v OFS='\t' -v ncols=6 '{ n=(NF>ncols)? NF: ncols; flag=0;
            for(i=1; i<=n; i++){ if($i==""){ flag+=1 }}; if (flag ==0) {print}}'  < $inp > $out && touch $out._OK
        wc -l $inp $out
    done
}

[[ $# -ne 1 || $1 == "-h" ]] && {
    echo "Usage: $0 <command> [args]"
    echo "Commands:"
    echo "  score-all"
    echo "  format-refless"
    echo "  spm-length"
    echo "  clean-refless"
    exit 1
}

$@
