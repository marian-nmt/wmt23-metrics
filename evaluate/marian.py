#!/usr/bin/env python

import sys
import argparse
import logging as log
from pathlib import Path
import subprocess
import threading
import itertools
from typing import Iterator, Optional, List, Union, Tuple
import shutil


log.basicConfig(level=log.INFO)
DEBUG_MODE=False

def copy_files_to_stdin(proc, src_file: Path, mt_file: Path):
    """Write data to subproc stdin. Note: run this on another thread to avoid deadlock
    This function reads two parallel files (src_file and mt_file), and write them as TSV record to the stdin of the sub process.
    :param proc: subprocess object to write to
    :param src_file: path to source file
    :param mt_file: path to MT file
    """

    with src_file.open() as src_lines, mt_file.open() as mt_lines:
        copy_stream_to_stdin(proc, src_lines, mt_lines)


def copy_stream_to_stdin(proc, srcs: Iterator[str], mts: Iterator[str]):
    """Write data to subproc stdin. Note: run this on another thread to avoid deadlock
    This function reads streams, and write them as TSV record to the stdin of the sub process.
    :param proc: subprocess object to write to
    :param srcs: stream of source lines
    :param mts: stream of mts
    """

    for src_line, mt_line in itertools.zip_longest(srcs, mts):
        if src_line is None or mt_line is None:
            log.error(f'Input files have different number of lines')
            raise ValueError('Input files have different number of lines')
        line = src_line.rstrip('\n') + '\t' + mt_line.rstrip('\n') + '\n'
        proc.stdin.write(line)
    proc.stdin.flush()
    proc.stdin.close()   # close stdin to signal end of input



def marian_score(model: Path, src_data: Union[Path, Iterator[str]], mt_data: Union[Path, Iterator[str]],
                vocab:Path=None, devices:Optional[List[int]]=None,
                width=4, mini_batch=16, like='comet-qe') -> Iterator[Union[float, Tuple[float, float]]]:
    """Run marian subprocess, write input and and read scores
    Depending on the `model` argument, either a single score or a tuple of scores is returned per input line.
    :param model: path to model file, or directory containing model.npz.best-embed.npz
    :param src_data: path to source file or stream of source lines
    :param mt_data: path to MT file or stream of mt lines
    :param vocab: path to vocabulary file (optional; if not given, assumed to be in the same directory as the model)
    :param devices: list of GPU devices to use (optional; if not given, decision is let to marian process)
    :param width: float precision
    :param mini_batch: mini-batch size (default: 16)
    :param like: marian embedding model like (default: comet-qe)
    :return: iterator over scores.
    """

    assert model.exists()
    if model.is_dir():
        model_dir = model
        #model_file = model / 'model.npz.best-embed.npz'
        model_file = model / "model.npz.best-ce-mean.npz"
    else:
        assert model.is_file()
        model_dir = model.parent
        model_file = model
    if not vocab:
        vocab = model_dir / 'vocab.spm'
    assert model_file.exists(), f'{model_file} does not exist'
    assert vocab.exists(), f'{vocab} does not exist'

    kwargs = dict(
        model=model_file,
        vocabs=(vocab, vocab),
        devices=devices,
        width=width,
        like=like,
        mini_batch=mini_batch,
        maxi_batch=100,
        max_length=512,
        max_length_crop=True,
        workspace=-4000,    # negative memory => relative to total memory
    )

    cmd_line = ['marian', 'evaluate']
    for key, val in kwargs.items():
        if val is None or val is False:   # ignore this key / flag
            continue
        cmd_line.append(f"--{key.replace('_', '-')}")
        if val is True:   # boolean flag, no value needs to be passed
            continue
        if isinstance(val, (list, tuple)):
            cmd_line.extend(str(v) for v in val)
        else:
            cmd_line.append(str(val))
    if not DEBUG_MODE:
        cmd_line.append('--quiet')

    proc = None
    try:
        proc = subprocess.Popen(cmd_line, shell=False, stdout=subprocess.PIPE, stdin=subprocess.PIPE,
                                stderr=sys.stderr, text=True, encoding='utf8', errors='replace')
        log.info(f'Running command: {" ".join(cmd_line)}')
        if isinstance(src_data, Path):
            copy_thread = threading.Thread(target=copy_files_to_stdin, args=(proc, src_data, mt_data))
        else:
            copy_thread = threading.Thread(target=copy_stream_to_stdin, args=(proc, src_data, mt_data))

        copy_thread.start()
        # read output and yield scores
        for line in proc.stdout:
            line = line.rstrip()
            if ' ' in line:
                yield tuple(float(x) for x in line.split(' '))
            else:
                yield float(line)

        # wait for copy thread to finish
        copy_thread.join()
        #proc.stdin.close()

        returncode = proc.wait()
        if returncode != 0:
            raise RuntimeError(f'Process exited with code {returncode}')
    finally:
        if proc is not None and proc.returncode is None:
            log.warning(f'Killing process {proc.pid}')
            proc.kill()


def parse_args():
    parser = argparse.ArgumentParser(
         formatter_class=argparse.ArgumentDefaultsHelpFormatter)

    parser.add_argument('-m', '--model', help='Model dir path', type=Path, required=True)
    parser.add_argument('-t', '--mt',  dest='mt_file', help='Input file', type=Path, required=True)
    parser.add_argument('-s', '--src', dest='src_file', help='Source file', type=Path, required=True)
    parser.add_argument('-o', '--out', default=sys.stdout, help='output file. Default stdout', type=argparse.FileType('w'))
    parser.add_argument('-w', '--width', default=4, help='Output score width', type=int)
    parser.add_argument('--debug', help='Verbose output', action='store_true')
    parser.add_argument('-d', '--devices', nargs='*', type=int, help='GPU device IDs')
    args = parser.parse_args()
    return vars(args)

def main(**args):
    args = args or parse_args()
    if args.pop('debug'):
        log.getLogger().setLevel(log.DEBUG)
        global DEBUG_MODE
        DEBUG_MODE=True
        log.debug(args)
    marian_bin_path = shutil.which('marian')
    if marian_bin_path is None:
        raise FileNotFoundError('marian binary not found in PATH')

    # Goal is to get output as iterator instead of directly writing to file in marian
    out = args.pop('out')
    scores = marian_score(**args)
    width = args.get('width', 4)
    for i, score in enumerate(scores):
        if isinstance(score, (tuple, list)):
            score = score[0]  # the first score
        out.write(f'{score:.{width}f}\n')
    out.close()

    log.info(f'Wrote {i} lines to {out.name}')

if '__main__' == __name__:
    main()
