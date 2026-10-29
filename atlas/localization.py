from opencc import OpenCC
import re
_converter=OpenCC('s2twp')
def to_hant(value):
    text=_converter.convert(str(value))
    for before,after in [('幹葉','乾葉'),('幹辣椒','乾辣椒'),('幹薑','乾薑'),('幹果','乾果')]:text=text.replace(before,after)
    return text

def scientific_english(value):
    """Translate display annotations while preserving the stored scientific field."""
    notes={'属':'genus','屬':'genus','原料属':'ingredient genus','原料屬':'ingredient genus',
           '种':'species','種':'species','亚种':'subspecies','亞種':'subspecies'}
    text=str(value or '').replace('（','(').replace('）',')')
    text=re.sub(r'(?<=\w)\(', ' (', text)
    return re.sub(r'\(([^()]*)\)',lambda m:'('+notes.get(m[1], 'source annotation' if re.search(r'[\u3400-\u9fff]',m[1]) else m[1])+')',text)
