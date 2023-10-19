#!/usr/bin/env python
import sys
import argparse
import logging as log
from pathlib import Path
from xml.etree import ElementTree as ET
from typing import Iterator, Tuple, List, Dict
from dataclasses import dataclass
from html import unescape
from collections import defaultdict
from lxml import etree     #LXML is robust and can recover from errors in input

from mtdata.iso import iso3_code

log.basicConfig(level=log.INFO)


def clean(text: str) -> str:
    return  ' '.join(unescape(text).split())

def extract_segs(tree: ET) -> Tuple[str,str]:       # -> Dict[str, str]:
    segs = [(seg.get('id', '').strip(), clean(seg.text or '')) for seg in tree.findall('.//seg')]
    if len(segs) != len(set(seg[0] for seg in segs)):
        log.warning(f'duplicate seg ids found in {tree.get("id") or tree.get("docid")}')
    return segs
    #return dict(segs)

lang_map = {
    'english': 'en',
    'german': 'de',
    'czech': 'cs',
    'spanish': 'es',
    'french': 'fr',
    'cz': 'cs',
}

def lang2code(x, stdize=False):
    x = x and lang_map.get(x.lower(), x) or x
    if stdize:
        x = iso3_code(x)
    return x

@dataclass
class WmtDoc:
    id: str
    lang: str # orig lang
    src: List[Tuple[str, str]]
    refs: List['WmtDocTrans']
    hyps: List['WmtDocTrans']

    def __post_init__(self):
        self.lang = lang2code(self.lang)

@dataclass
class WmtDocTrans:
    id: str
    lang: str
    by: str
    is_human: bool
    segs: List[Tuple[str, str]] # [(id, text), ...]
    def __post_init__(self):
        self.lang = lang2code(self.lang)


def parse_wmt21_xml(data: Path) -> Iterator[WmtDoc]:
    with open(data, encoding='utf8') as data:
        root = ET.parse(data)
        count = 0
        for doc in root.findall('.//doc'):
            # Get the attributes of the doc element
            docid = doc.get('id')
            srcs = doc.findall('.//src')
            assert len(srcs) == 1, f'single source expected but found {len(srcs)}'
            src_segs = extract_segs(srcs[0])
            result = WmtDoc(id=docid, lang=doc.get('origlang'), src=src_segs, refs=[], hyps=[])

            ref_docs = doc.findall('.//ref') or []
            hyp_docs = doc.findall('.//hyp') or []
            if not ref_docs or not hyp_docs:
                log.warning(f'doc {docid} has {len(ref_docs)} refs and {len(hyp_docs)} hyps')

            for ref_doc in ref_docs:
                tgt_doc = WmtDocTrans(id=docid, lang=ref_doc.get('lang'),
                                    by=ref_doc.get('translator'), is_human=True,
                                    segs=extract_segs(ref_doc))
                result.refs.append(tgt_doc)
            for hyp_doc in hyp_docs:
                tgt_doc = WmtDocTrans(id=docid, lang=hyp_doc.get('lang'),
                                    by=hyp_doc.get('system'), is_human=False,
                                    segs=extract_segs(hyp_doc))
                result.hyps.append(tgt_doc)
            yield result
            count += 1
        log.info(f"read {count} docs from {data.name.split('/')[-1]}")


def read_sgm_docs(src: Path, ref: Path, *hyps: List[Path], year: int=None) -> Iterator[WmtDoc]:
    parser = read_sgm_xml
    if year == 2010:
        parser = read_wmt10_xml

    src_doc = parser(src)
    ref_doc = parser(ref)
    hyp_docs = [parser(hyp) for hyp in hyps]
    # NOTE: WMT2020 has (extra/) human refs in the system outputs
    for docid, sdoc in src_doc.items():
        result = WmtDoc(id=docid, lang=sdoc['lang'], src=sdoc['segs'], refs=[], hyps=[])
        if docid in ref_doc:
            rdoc = ref_doc.get(docid)
            if len(sdoc['segs']) != len(rdoc['segs']):
                log.warning(f'number of segments in src and ref do not match {len(sdoc["segs"])} != {len(rdoc["segs"])}')
                continue
            result.refs.append(WmtDocTrans(id=docid, lang=rdoc['lang'], segs=rdoc['segs'], by=rdoc['by'], is_human=rdoc['is_human']))
        for hyp_file, hdoc in zip(hyps, hyp_docs):
            if docid not in hdoc:
                log.warning(f'doc {docid} not found in {hyp_file.name}')
                continue
            hdoc = hdoc[docid]
            if len(sdoc['segs']) != len(hdoc['segs']):
                log.warning(f'number of segments in src and hyp do not match  {len(sdoc["segs"])} != {len(hdoc["segs"])}')
                continue
            result.hyps.append(WmtDocTrans(id=docid, lang=hdoc['lang'], segs=hdoc['segs'], by=hdoc['by'], is_human=hdoc['is_human']))
        yield result

def read_sgm_xml(path: Path) -> Iterator[str]:
    root = parse_xml_tree(path)
    result = {}
    is_source = root.tag == 'srcset'
    tgt_lang = root.get('trglang')
    for doc in root.xpath('.//doc'):
        docid = doc.get('docid')
        origlang = doc.get('origlang')
        sysid = doc.get('sysid')
        segs = extract_segs(doc)
        lang = origlang if is_source else tgt_lang
        result[docid] = dict(id=docid, lang=lang, segs=segs, by=sysid, is_human=sysid == 'ref')
    return result


def read_wmt10_xml(path: Path, year=2010):
    root = parse_xml_tree(path, year=year)
    result = {}
    set_el = root.xpath('//mteval/*[1]')[0]
    lang, sysid = '', ''
    if set_el.tag == 'srcset':
        lang = set_el.get('srclang')
    elif set_el.tag == 'refset':
        lang = set_el.get('trglang')
        sysid = set_el.get('refid')
    elif set_el.tag == 'tstset':
        lang = set_el.get('trglang')
        sysid = set_el.get('sysid')
    else:
        log.warning(f'{set_el.tag} is unexpected')
    for doc in root.xpath('.//doc'):
        docid = doc.get('docid')
        segs = extract_segs(doc)
        result[docid]= dict(id=docid, lang=lang, segs=segs, by=sysid, 
                            is_human=sysid.startswith('reference') or sysid == '_ref')
    return result

def parse_xml_tree(path: Path, year=None) -> etree.ElementTree:
    # some files arent XML/HTML escaped. so we read it as string and escape
    if not path.exists():
        raise Exception(f'{path} not found')
    encoding_trials = ['utf8', 'latin1']
    data = None
    for encoding in encoding_trials:
        try:
            with open(path, encoding=encoding, errors='replace') as stream:
                data = stream.read()
                if encoding != 'utf8':
                    data = data.encode(encoding, errors='replace').decode('utf8')
                break
        except:
            log.warning(f'Unable to read file {path} using {encoding}')
    if not data:
        raise Exception(f'Unable to read file {path} using any of the encodings {encoding_trials}')
    data = data.replace('<DOC ', '<doc ') # some files have <DOC> instead of <doc>
    if year in (2010, 'wmt10'):
        # these files got <?xml encoding="UTF-8"> which requires byte array input
        data = data.encode('utf-8')  # to bytes
    try:
        #data = data.replace('&', '&amp;')
        #root = ET.fromstring(data)
        parser = etree.XMLParser(recover=True, encoding='utf-8')
        root = etree.fromstring(data, parser=parser)
        return root
    except:
        log.error(f'error parsing {path}')
        raise


def write_out_multifile(docs: List[WmtDoc], out_dir: Path, langs:Tuple[str, str], year):

    src_lang, tgt_lang = lang2code(langs[0], stdize=True), lang2code(langs[1], stdize=True)
    pref = f'{out_dir}/{src_lang}-{tgt_lang}/{src_lang}-{tgt_lang}'
    Path(pref).parent.mkdir(parents=True, exist_ok=True)
    src_file = f'{pref}.{src_lang}.src.txt'
    meta_file = f'{pref}.meta.tsv'

    fopen_cache = {}
    def maybe_open(path, mode='w'):
        if path not in fopen_cache:
            fopen_cache[path] = open(path, mode=mode, encoding='utf-8', errors='replace')
        return fopen_cache[path]

    # WMT21 onwards not all trabslations have translated  all docs
    MISSING_SEG='<<MISSING>>'
    UNKNOWN_NAME='__UNKNOWN__'

    def norm_name(name):
        if not name:
            name = UNKNOWN_NAME
        return name.replace('.', '_')

    try:
        all_ref_names = {norm_name(ht_doc.by) for doc in docs for ht_doc in doc.refs }

        for doc in docs:
            order = []
            src_out = maybe_open(src_file)
            meta_out = maybe_open(meta_file)

            for id, seg in doc.src:
                src_out.write(f'{seg}\n')
                meta_out.write(f'{year}\t{src_lang}-{tgt_lang}\t{doc.id}\t{id}\n')
                order.append(id)

            found_ref_names = {norm_name(ht_doc.by) for ht_doc in doc.refs }
            for suffix, tgt_docs in [('ref', doc.refs), ('hyp', doc.hyps)]:
                for tgt_doc in tgt_docs:
                    if suffix == 'hyp' and tgt_doc.by == 'ref':
                        log.warning(f'found a hyp that claims to be a ref skipping it')
                        continue
                    if not tgt_doc.by:
                        tgt_doc.by = UNKNOWN_NAME

                    name = tgt_doc.by.replace('.', '_')
                    ref_file = f'{pref}.{tgt_lang}.{name}.{suffix}.txt'
                    ref_out = maybe_open(ref_file)
                    lookup = {k: v for k, v in tgt_doc.segs}
                    for seg_id in order:
                        text = lookup.get(seg_id, MISSING_SEG)
                        ref_out.write(f'{text}\n')

            missing_hts = all_ref_names - found_ref_names
            for name in missing_hts:
                ref_file = f'{pref}.{tgt_lang}.{name}.ref.txt'
                ref_out = maybe_open(ref_file)
                for seg_id in order:
                    ref_out.write(f'{MISSING_SEG}\n')

    finally:
        for f in fopen_cache.values():
            f.close()

def main(**args):
    year = args['year']
    if year.startswith('wmt'):
        year = int(year[3:])
        if year < 100:
            year += 2000
    if year >= 2021:
        assert len(args['inp']) == 1, 'only one input file expected for wmt21'
        docs = parse_wmt21_xml(args['inp'][0])
    elif 2009 == year or 2011 <= year <= 2020:
        assert len(args['inp']) >= 3, 'At least three input files expected for wmt11-20'
        docs = read_sgm_docs(*args['inp'])
    elif year == 2010:
        assert len(args['inp']) >= 3, 'At least three input files expected for wmt11-20'
        docs = read_sgm_docs(*args['inp'], year=year)
    elif 2008 == year:
        raise Exception('WMT 2008 system XML files are malformed XML. They forgot to close </doc> tags for some. So I am skipping them for now :(')
    else:
        raise Exception(f'year {args["year"]} not supported yet')

    docs = list(docs)  # buffer in memory
    write_out_multifile(docs, args['out'], year=year, langs=args['langs'])


def parse_args():
    parser = argparse.ArgumentParser(
         formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('-i', '--inp', type=Path, nargs='+',
                        help='''Input file(s)
                        For wmt21: single XML file
                        for all others: 3+ files: src, ref, hyp1 [hyp2 ...],
                        ''')
    parser.add_argument('-o', '--out', required=True, help='output dir to store files', type=Path)
    parser.add_argument('-ol', '--origlang', help='original language. \
                        If given, non-original docs will be skipped. If missing, no filtering will be applied.')
    parser.add_argument('-y', '--year', help='wmt year', required=True)
    parser.add_argument('--langs', '--langs', help='source and target language', nargs=2, required=True)
    args = parser.parse_args()
    return vars(args)


if '__main__' == __name__:
    args = parse_args()
    try:
        main(**args)
    except:
        args = '\n  '.join(f'{k}={isinstance(v, list) and ",".join(map(str, v)) or v }' for k,v in args.items())
        log.warning(f'CLI args:\n  {args}\n')
        raise
