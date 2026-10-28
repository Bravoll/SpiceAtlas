from opencc import OpenCC
_converter=OpenCC('s2twp')
def to_hant(value):
    text=_converter.convert(str(value))
    for before,after in [('幹葉','乾葉'),('幹辣椒','乾辣椒'),('幹薑','乾薑'),('幹果','乾果')]:text=text.replace(before,after)
    return text
