#!/usr/bin/env bash
# created by Thamme Gowda on Dec 15, 2022
set -eu
mydir="$(realpath $(dirname ${BASH_SOURCE[0]}) )"
scripts="$(realpath $mydir/..)"

parse_xml="python $mydir/parse_wmt_xml.py"

###### settings ########
out_dir=/mnt/tg/projects/mt-metrics/2023-metric-distill/data/wmt-metrics
#######################
[[ -d $out_dir ]] || mkdir -p $out_dir

log() {
    echo "Line:${BASH_LINENO}:: $@" >&2
}

get_wmt_data(){
    # this function downloads news domain only
    local dir="$1"   # out dir
    #[[ -d $dir ]] || mkdir -p $dir
    echo "wmt22 https://github.com/wmt-conference/wmt22-news-systems/archive/refs/heads/main.tar.gz
    wmt21 https://github.com/wmt-conference/wmt21-news-systems/archive/refs/heads/main.tar.gz
    wmt20 https://drive.google.com/u/0/uc?id=1Wjn8AaQae6dcvd8oK7Qu4m8jITJ4g5o5&export=download&confirm=t
    wmt19 http://data.statmt.org/wmt19/translation-task/wmt19-submitted-data-v3.tgz
    wmt18 http://data.statmt.org/wmt18/translation-task/wmt18-submitted-data-v1.0.1.tgz
    wmt17 http://data.statmt.org/wmt17/translation-task/wmt17-submitted-data-v1.0.tgz
    wmt16 http://data.statmt.org/wmt16/translation-task/wmt16-submitted-data-v2.tgz
    wmt15 https://www.statmt.org/wmt15/wmt15-submitted-data.tgz
    wmt14 https://www.statmt.org/wmt14/submissions.tgz
    wmt13 https://www.statmt.org/wmt13/wmt13-data.tar.gz
    wmt12 https://www.statmt.org/wmt12/wmt12-data.tar.gz
    wmt11 https://www.statmt.org/wmt11/wmt11-data.tar.gz
    wmt10 https://www.statmt.org/wmt10/results/wmt10-data.zip
    wmt09 https://www.statmt.org/wmt09/wmt09-eval.tar.gz
    wmt08 https://www.statmt.org/wmt08/wmt08-eval.tar.gz
    wmt07 https://www.statmt.org/wmt07/submissions.tgz" |
    while read year url; do
        echo "Download and extract $year  $url"
        ext='tgz'
        if [[ $year == 'wmt10' ]]; then ext='zip'; fi
        dname=$dir/$year-submissions
        fname=$dname.$ext
        [[ -d $dname ]] || mkdir -p $dname
        if [[ ! -f $dname/_OK ]]; then
            # download file, if missing
            [[ -f $fname._OK ]] || wget "$url" -O $fname && touch $fname._OK
            # extract file
            if [[ $ext == "zip" ]]; then
                unzip $fname -d $dname
                mv $dname/wmt10-data/* $dname
                rm -rf $dname/wmt10-data
            else
                tar -xvf $fname -C $dname --strip-components=1
            fi
            touch $dname/_OK
        fi
    done
}

get_wmt_data $out_dir/downloads

extract_auth_segs(){
    local year=$1
    local inp_dir=$2
    local out_dir=$3
    [[ -d $inp_dir ]] || { log "$inp_dir does not exist"; return 1; }
    [[ -d $out_dir ]] || mkdir -p $out_dir
    flag=$out_dir/._OK_$year
    if [[ -f $flag ]]; then
        log "$flag exists... skipping..."
        return 0
    fi

    local prefix=newstest20${year/wmt/}
    local name="news"

    case $year in
        wmt21 | wmt22)
            for inp in $inp_dir/xml/*.all.xml; do
                IFS="." read name pair _ <<< "$(basename $inp)"  # name is like "newstest21.en-de.all.xml"
                IFS="-" read src tgt <<< "$pair"
                name=${name/test2021/}
                local out_subdir=$out_dir/$year.$name
                log "====$out_subdir===="
                $parse_xml -i $inp -o $out_subdir --year $year --langs $src $tgt #--origlang $src
            done
            ;;
        wmt20)
            inp_dir=$inp_dir/$prefix
            langs=$(ls -d $inp_dir/sgm/system-outputs/*/| xargs -I {} basename {})
            #langs="cs-en de-en de-fr en-cs en-de en-iu en-ja en-km en-pl en-ps en-ru en-ta en-zh fr-de iu-en ja-en km-en pl-en ps-en ru-en ta-en zh-en"
            for pair in $langs; do
                IFS='-' read src tgt <<< "$pair"
                local out_subdir=$out_dir/$year.$name
                log "====$pair  :: $out_subdir===="
                src_file=$inp_dir/sgm/sources/$prefix-${src}${tgt}-src.$src.sgm
                ref_file=$inp_dir/sgm/references/$prefix-${src}${tgt}-ref.$tgt.sgm
                hyp_files=$(echo $inp_dir/sgm/system-outputs/$pair/$prefix.$pair.*.sgm)
                $parse_xml -o $out_subdir --year $year -i $src_file $ref_file $hyp_files  --langs $src $tgt # --origlang $src
            done   # TODO: add wmt20 newtestB
            ;;
          wmt14 | wmt15 | wmt16 | wmt17 | wmt18 | wmt19)
            langs=$(ls -d $inp_dir/sgm/system-outputs/$prefix/*/| xargs -I {} basename {})
            for pair in $langs; do
                IFS='-' read src tgt <<< "$pair"
                local out_subdir=$out_dir/$year.$name
                log "====$pair :: $out_subdir===="
                src_file=$inp_dir/sgm/sources/$prefix-${src}${tgt}-src.$src.sgm
                ref_file=$inp_dir/sgm/references/$prefix-${src}${tgt}-ref.$tgt.sgm
                hyp_files=$(echo $inp_dir/sgm/system-outputs/$prefix/$pair/$prefix.*.$pair.sgm)  # newstest2014.JHU.cs-en.sgm

                [[ -f $src_file ]] || { log "Source file $src_file does not exist... skipping";  continue; }

                $parse_xml -o $out_subdir  --year $year -i $src_file $ref_file $hyp_files --langs $src $tgt #--origlang $src
            done
            ;;
        wmt11 | wmt12 | wmt13 )
            langs=$(ls -d $inp_dir/sgm/system-outputs/$prefix/*/| xargs -I {} basename {})
            for pair in $langs; do
                IFS='-' read src tgt <<< "$pair"
                local out_subdir=$out_dir/$year.$name
                log "====$pair :: $out_subdir===="
                src_file=$inp_dir/sgm/sources/$prefix-src.$src.sgm
                ref_file=$inp_dir/sgm/references/$prefix-ref.$tgt.sgm
                hyp_files=$(echo $inp_dir/sgm/system-outputs/$prefix/$pair/$prefix.$pair.*.sgm)  #newstest2013.cs-en.JHU.2903.sgm
                $parse_xml -o $out_subdir --year $year -i $src_file $ref_file $hyp_files --langs $src $tgt #--origlang $src
            done
            ;;
        wmt10 )
            prefix=newssyscombtest20${year/wmt/}
            langs=$(ls -d $inp_dir/xml/tst-primary/*/| xargs -I {} basename {})
            for pair in $langs; do
                IFS='-' read src tgt <<< "$pair"
                local out_subdir=$out_dir/$year.$name
                log "====$pair :: $out_subdir===="
                src_file=$inp_dir/xml/src/$prefix.$src.src.xml
                ref_file=$inp_dir/xml/ref/$prefix.$pair.ref.xml
                hyp_files=$(echo $inp_dir/xml/tst-{primary,secondary}/$pair/$prefix.$pair.*.xml)  #newstest2013.cs-en.JHU.2903.sgm
                $parse_xml -o $out_subdir --year $year -i $src_file $ref_file $hyp_files --langs $src $tgt #--origlang $src
                break;
            done
            ;;
        wmt09 )
            langs=$(ls -d $inp_dir/submissions-xml/*/ | xargs -I {} basename {})
            for pair in $langs; do
                IFS='-' read src tgt <<< "$pair"
                local out_subdir=$out_dir/$year.$name
                log "====$pair :: $out_subdir===="
                src_file=$inp_dir/source+ref-xml/$prefix-src.$src.xml
                [[ -f $src_file ]] || { log "$src_file not found. skipping"; continue; }
                ref_file=$inp_dir/source+ref-xml/$prefix-ref.$tgt.xml
                hyp_files=$(echo $inp_dir/submissions-xml/$pair/$pair.$prefix.*.xml)
                ls $hyp_files &> /dev/null || { log "$hyp_files not found"; continue; }
                $parse_xml -o $out_subdir --year $year -i $src_file $ref_file $hyp_files --langs $src $tgt # --origlang $src
            done
            ;;
        * )
            log "ERROR $year not supported yet"
            exit 3;
            ;;
    esac
    touch $flag
}

sanity_check() {
    local src_files="$@"
    local prefix lines1 n1 n2 i
    for src_file in $src_files; do
        [[ -f $src_file ]] || { log "ERROR: $src_file not found"; exit 1; }
        n1=$(wc -l < $src_file)
        prefix=${src_file%.*.src.txt}
        local n_errs=0
        for i in $prefix.*; do
            n2=$(wc -l < $i)
            [[ $n1 -eq $n2 ]] || {
                log "ERROR: $prefix ${src_file/$prefix/} and ${i/$prefix/} have different number of lines: ${n1} != ${n2}"
                n_errs=$((n_errs+1))
            }
        done
        log "$prefix : $n_errs errors"
    done
}


readonly years="$(echo wmt{09..22})"
#readonly years="wmt20"
for year in $years; do
    extract_auth_segs $year "$out_dir/downloads/$year-submissions" "$out_dir/extracts"
done
# uncomment for sanity checks
# sanity_check $(echo $out_dir/extracts/*/*/*.src.txt)


: '
We have:
* .src.txt  (x 1)
* .meta.tsv (x 1)
* .ref.txt  (x 1+)
* .hyp.txt  (x 1+)

We want TSV files:
Year Pair TestName Sysname docID SentID src ref hyp
2023 cs-en newstest2023 JHU 1 1 src.txt ref.txt hyp.txt
'

echo_n(){
    local n=$1
    local s=$2
    for ((i=0; i<$n; i++)); do
        echo -e "$s"
    done
}
merge_dataset_as_tsv(){
    local src_files="$@"
    local prefix lines1 n1 n2 pair meta_file
    for src_file in $src_files; do
        [[ -f $src_file ]] || { log "ERROR: $src_file not found"; exit 1; }
        n1=$(wc -l < $src_file)
        prefix=${src_file%.*.src.txt}
        pair=$(basename $prefix)
        IFS=- read src tgt <<< "$pair"
        meta_file=$prefix.meta.tsv
        [[ $n1 -eq $(wc -l < $meta_file) ]] || { log "ERROR: $src_file and $meta_file have different number of lines"; exit 1; }
        for ref_file in $prefix.*.ref.txt; do
            [[ $n1 -eq $(wc -l < $ref_file) ]] || {
                log "ERROR: $src_file and $ref_file have different number of lines";
                continue;
            }
            ref_name=${ref_file/$prefix.$tgt./}
            ref_name=${ref_name/.ref.txt/}
            [[ $ref_name =~ ref* ]] || ref_name="ref"

            for hyp_file in $prefix.*.hyp.txt; do
                [[ -f $hyp_file ]] || { log "Skip $hyp_file: not found"; continue;}
                n2=$(wc -l < "$hyp_file")
                [[ $n1 -eq $n2 ]] || { log "Skip $hyp_file: $n1 != $n2"; continue; }
                hyp_name=${hyp_file/$prefix.$tgt.}
                hyp_name=${hyp_name/.hyp.txt/}
                #echo "$prefix ${meta_file/$prefix} ${src_file/$prefix} $ref_name $hyp_name"
                paste <(cut -f1,2,3 "$meta_file") <(echo_n $n1 "$ref_name $hyp_name") "$src_file" "$ref_file" "$hyp_file"
            done
        done
    done
}

mkdir -p $out_dir/tsvs
for year in $years; do
    out_file=$out_dir/tsvs/$year.tsv
    [[ -f $out_file._OK ]] && { log "Skip $out_file"; continue; }
    log "Merging $year"
    # TODO: remove <<MISSING>> segments
    rm -f $out_file $out_file._OK
    merge_dataset_as_tsv $(echo $out_dir/extracts/$year.*/*/*.src.txt) \
        | tee >( grep '<<MISSING>>' > $out_file._ERRORS) \
        | grep -v '<<MISSING>>' >  $out_file && touch $out_file._OK
done

wmt_22=$out_dir/merged/wmt22.tsv
wmt_sans22=$out_dir/merged/wmt_sans22.tsv
[[ -f $wmt_sans22._OK ]] || {
    mkdir -p $(dirname $wmt_sans22)
    rm -f $wmt_sans22 $wmt_22
    cat $out_dir/tsvs/wmt{09..21}.tsv > $wmt_sans22
    cp $out_dir/tsvs/wmt22.tsv $wmt_22
    touch $wmt_sans22._OK
}

# there are 4M segments (sans22); keep 400k for dev, 3.6M for train
# shuffle docs
shuf_file=${wmt_sans22%.tsv}.shuf.tsv
dev_file=${wmt_sans22%.tsv}.dev.tsv
train_file=${wmt_sans22%.tsv}.train.tsv
[[ -f $shuf_file._OK ]] || {
    rm -f $shuf_file $shuf_file._OK $dev_file $train_file
    log "Shuffling $wmt_sans22"
    python $mydir/shuffledocs.py -k 4 < $wmt_sans22 > $shuf_file
    log "Splitting $shuf_file"
    head -n 400000 $shuf_file > ${shuf_file%.tsv}.dev.tsv
    awk 'NR>400000' $shuf_file > ${shuf_file%.tsv}.train.tsv
    touch $shuf_file._OK
}

echo "ALL DONE"
exit 0

