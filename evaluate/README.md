## Setup 

Requires python 3.9+; if you are using older OS where 3.8 is default, create a conda environment.

```bash
pip install -r requirements.txt
```

```bash
python -m evaluate -h 
usage: evaluate [-h] [-b DIR] [-t TESTSET] {validate,full,report} ...

positional arguments:
  {validate,full,report}
                        Sub-commands
    validate            Validation mode: scores file is given, print only single number (accuracy). This is useful for hyperparameter tuning. The
                        given scores are NOT cached.
    full                Model evaluation (full) mode. Given a model dir (e.g. marian model), score all testset systems, evaluate and show ranking.
                        This mode caches scores under --user-dir for subsequent use.
    report              Report mode: report results for all metrics in --base-dir and --user-dir

options:
  -h, --help            show this help message and exit
  -b DIR, --base-dir DIR
                        mt-metrics-eval dir (default: /mnt/tg/projects/mt-metrics/2023-metric-distill/evals/mt-metrics-eval-v2)
  -t TESTSET, --testset TESTSET
                        Testset name (default: wmt22)
```


## Full evaluation

Given a model, score the files, and then evaluate.

* Add `marian` bin to PATH

```bash
python -m evaluate full -h 
usage: evaluate full [-h] [-n METRIC_NAME] [--ref] [--no-ref] [-u DIR] model

positional arguments:
  model                 Model dir path

options:
  -h, --help            show this help message and exit
  -n METRIC_NAME, --name METRIC_NAME
                        Name for metric. Optional: derives from the model dir name (default: None)
  --ref                 Reference-based metric. Default is reference-free. (default: False)
  --no-ref              Reference-based metric. Default is reference-free. (default: True)
  -u DIR, --user-dir DIR
                        Directory for caching your own metrics (default: /mnt/tg/projects/mt-metrics/2023-metric-distill/evals/user-metrics)
# example
python -m evaluate full path/to/marian-model
# path is the output from marian/train.sh
```


`model` argument should be full path to marian model dir created by `scripts/marian/train.sh`
Example:

```bash
$ ls -1d /mnt/tg/projects/mt-metrics/2023-metric-distill/runs/marian/dd*
/mnt/tg/projects/mt-metrics/2023-metric-distill/runs/marian/dd001-comet22daref-r1
/mnt/tg/projects/mt-metrics/2023-metric-distill/runs/marian/dd002-gemba-dav003-noref-r1
/mnt/tg/projects/mt-metrics/2023-metric-distill/runs/marian/dd003-gemba-dav003-ref-r1
/mnt/tg/projects/mt-metrics/2023-metric-distill/runs/marian/dd004-gembav3-noref-r1
/mnt/tg/projects/mt-metrics/2023-metric-distill/runs/marian/dd005-gembav3-highreg-noref-r1
```


## Get flat files

```bash

python -m evaluate flatten -h 
usage: evaluate flatten [-h] [--ref] [--no-ref] [--human {none,wmt-appraise,wmt-z,wmt,mqm}] [--no-human NO_HUMAN]

optional arguments:
  -h, --help            show this help message and exit
  --ref                 Reference-based metric. Default is reference-free. (default: False)
  --no-ref              Reference-based metric. Default is reference-free. (default: True)
  --human {none,wmt-appraise,wmt-z,wmt,mqm}
                        Human scores name (default: None)
  --no-human NO_HUMAN, --testset NO_HUMAN
                        Testset name (default: wmt22)
```

```bash
for n in none wmt-appraise wmt-z wmt mqm; do
  python -m evaluate flatten --human $n
done
```

## Validation mode

In this mode, specify a scored file and get a single real number in STDOUT. To be used for hyper param tuning.

```bash
 python -m evaluate validate -h 
usage: evaluate validate [-h] [-w INT] [-sc {wmt22.mqm_tab11,wmt22.dasqm_tab11,wmt22.da_sqm_tab8}] [--ref] [--no-ref] scores

positional arguments:
  scores                Scores file path

options:
  -h, --help            show this help message and exit
  -w INT, --width INT   Digits in float after decimal point (default: 6)
  -sc {wmt22.mqm_tab11,wmt22.dasqm_tab11,wmt22.da_sqm_tab8}, --scenario {wmt22.mqm_tab11,wmt22.dasqm_tab11,wmt22.da_sqm_tab8}
                        Evaluation Scneario (default: wmt22.da_sqm_tab8)
  --ref                 Reference-based metric. Default is reference-free. (default: False)
  --no-ref              Reference-based metric. Default is reference-free. (default: True)
```

Each line in the given `<scores>` file should have a single real number (e.g., segment level score) and should have the same number of lines and order as the data file at `<base-dir>/<taskname>.noref.tsv`. 

Example _data file_ for wmt22: `/mnt/tg/projects/mt-metrics/2023-metric-distill/evals/mt-metrics-eval-v2/wmt22.noref.tsv`
This _data file_ is created automatically under --base-dir path on the first run (of `full` or `validate` subcommands). The fields in TSV are of format `<langs> <refname> <sysname> <source_seg> <ref_seg> <hyp_seg>`. 

> NOTE: for a referenceless metric, run `cut -f4,6 path.tsv` to extract source and hypothesis seqments.

## Produce evaluation report

```bash
python -m evaluate report -h 
usage: evaluate report [-h] [-u DIR] [-o FILE]

options:
  -h, --help            show this help message and exit
  -u DIR, --user-dir DIR
                        Directory when your metrics are cached (default: /mnt/tg/projects/mt-metrics/2023-metric-distill/evals/user-metrics)
  -o FILE, --report-file FILE
                        Output file path (default: results.csv)
```

----

## Unbabel model scoring

`python -m evaluate full` has `--toolkit unbabel`

Set -m to full checkpoint path for unabel comet. 
Example: 

```bash
$model=/mnt/tg/projects/mt-metrics/2023-metric-distill/runs/unbabel/uc001-gembav3.1-noref/checkpts/epoch\=3-step\=113065-val_kendall\=0.292.ckpt
python -m evaluate full $model -t unbabel -n uc001-gembav3.1-ep3step113k
```

In addition, you may need to create `hparams.yaml`, which is our model config.yaml with minor tweaks.

See `/mnt/tg/projects/mt-metrics/2023-metric-distill/runs/unbabel/uc001-gembav3.1-noref/hparams.yaml`
or https://huggingface.co/Unbabel/wmt20-comet-qe-da/blob/main/hparams.yaml 

