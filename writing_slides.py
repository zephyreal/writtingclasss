"""Small editable OOXML lecture decks. No external presentation API or runtime."""
import io
import zipfile
from xml.sax.saxutils import escape

P='http://schemas.openxmlformats.org/presentationml/2006/main'
A='http://schemas.openxmlformats.org/drawingml/2006/main'
R='http://schemas.openxmlformats.org/officeDocument/2006/relationships'
REL='http://schemas.openxmlformats.org/package/2006/relationships'
GROUP='<p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr><p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/><a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr>'

def xml(text):return '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'+text
def safe(text):return escape(''.join(c for c in str(text) if c in '\n\t\r' or ord(c)>=32))
def relationships(items):
    return xml(f'<Relationships xmlns="{REL}">'+''.join(f'<Relationship Id="rId{i}" Type="{R}/{kind}" Target="{target}"/>' for i,kind,target in items)+'</Relationships>')

def box(i,text,x,y,w,h,size,color):
    paragraphs=''.join(f'<a:p><a:pPr/><a:r><a:rPr lang="zh-CN" sz="{size}" dirty="0"><a:solidFill><a:srgbClr val="{color}"/></a:solidFill><a:latin typeface="Aptos"/><a:ea typeface="Microsoft YaHei"/></a:rPr><a:t>{safe(line)}</a:t></a:r><a:endParaRPr lang="zh-CN" sz="{size}"/></a:p>' for line in text.split('\n'))
    return f'<p:sp><p:nvSpPr><p:cNvPr id="{i}" name="Text {i}"/><p:cNvSpPr txBox="1"/><p:nvPr/></p:nvSpPr><p:spPr><a:xfrm><a:off x="{x}" y="{y}"/><a:ext cx="{w}" cy="{h}"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom><a:noFill/><a:ln><a:noFill/></a:ln></p:spPr><p:txBody><a:bodyPr wrap="square" lIns="0" rIns="0" tIns="0" bIns="0"><a:spAutoFit/></a:bodyPr><a:lstStyle/>{paragraphs}</p:txBody></p:sp>'

def split_body(text):
    # Conservative Chinese wrapping and pagination instead of shrinking long text.
    lines=[]
    for paragraph in text.split('\n'):
        lines.extend([paragraph[i:i+36] for i in range(0,len(paragraph),36)] or [''])
    return ['\n'.join(lines[i:i+9]) for i in range(0,len(lines),9)] or ['']

def build_pptx(brief):
    slides=[{'title':brief['title']+('（续）' if n else ''),'body':chunk} for n,chunk in enumerate(split_body(brief['summary']))]
    for slide in brief['slides']:
        chunks=split_body(slide['body'])
        for n,chunk in enumerate(chunks):slides.append({'title':slide['title']+('（续）' if n else ''),'body':chunk})
    output=io.BytesIO()
    with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as z:
        overrides=[('/ppt/presentation.xml','presentationml.presentation.main'),('/ppt/slideMasters/slideMaster1.xml','presentationml.slideMaster'),('/ppt/slideLayouts/slideLayout1.xml','presentationml.slideLayout'),('/ppt/theme/theme1.xml','theme')]
        overrides += [(f'/ppt/slides/slide{i}.xml','presentationml.slide') for i in range(1,len(slides)+1)]
        z.writestr('[Content_Types].xml',xml('<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/>'+''.join(f'<Override PartName="{path}" ContentType="application/vnd.openxmlformats-officedocument.{kind}+xml"/>' for path,kind in overrides)+'</Types>'))
        z.writestr('_rels/.rels',relationships([(1,'officeDocument','ppt/presentation.xml')]))
        z.writestr('ppt/presentation.xml',xml(f'<p:presentation xmlns:p="{P}" xmlns:a="{A}" xmlns:r="{R}"><p:sldMasterIdLst><p:sldMasterId id="2147483648" r:id="rId1"/></p:sldMasterIdLst><p:sldIdLst>'+''.join(f'<p:sldId id="{255+i}" r:id="rId{i+1}"/>' for i in range(1,len(slides)+1))+'</p:sldIdLst><p:sldSz cx="12192000" cy="6858000" type="screen16x9"/><p:notesSz cx="6858000" cy="9144000"/></p:presentation>'))
        z.writestr('ppt/_rels/presentation.xml.rels',relationships([(1,'slideMaster','slideMasters/slideMaster1.xml')]+[(i+1,'slide',f'slides/slide{i}.xml') for i in range(1,len(slides)+1)]))
        mapping='<p:clrMap accent1="accent1" accent2="accent2" accent3="accent3" accent4="accent4" accent5="accent5" accent6="accent6" bg1="lt1" bg2="lt2" folHlink="folHlink" hlink="hlink" tx1="dk1" tx2="dk2"/>'
        z.writestr('ppt/slideMasters/slideMaster1.xml',xml(f'<p:sldMaster xmlns:p="{P}" xmlns:a="{A}" xmlns:r="{R}"><p:cSld><p:spTree>{GROUP}</p:spTree></p:cSld>{mapping}<p:sldLayoutIdLst><p:sldLayoutId id="2147483649" r:id="rId1"/></p:sldLayoutIdLst><p:txStyles><p:titleStyle/><p:bodyStyle/><p:otherStyle/></p:txStyles></p:sldMaster>'))
        z.writestr('ppt/slideMasters/_rels/slideMaster1.xml.rels',relationships([(1,'slideLayout','../slideLayouts/slideLayout1.xml'),(2,'theme','../theme/theme1.xml')]))
        z.writestr('ppt/slideLayouts/slideLayout1.xml',xml(f'<p:sldLayout xmlns:p="{P}" xmlns:a="{A}" xmlns:r="{R}" type="blank" preserve="1"><p:cSld name="Blank"><p:spTree>{GROUP}</p:spTree></p:cSld><p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr></p:sldLayout>'))
        z.writestr('ppt/slideLayouts/_rels/slideLayout1.xml.rels',relationships([(1,'slideMaster','../slideMasters/slideMaster1.xml')]))
        colors={'dk1':'172D39','lt1':'FFFFFF','dk2':'234553','lt2':'F4F7F8','accent1':'167D8D','accent2':'E09B58','accent3':'5D8093','accent4':'659B88','accent5':'827FA6','accent6':'AE755C','hlink':'167D8D','folHlink':'827FA6'}
        color_xml=''.join(f'<a:{k}><a:srgbClr val="{v}"/></a:{k}>' for k,v in colors.items())
        fills='<a:solidFill><a:schemeClr val="phClr"/></a:solidFill>'
        line='<a:ln w="9525"><a:solidFill><a:schemeClr val="phClr"/></a:solidFill><a:prstDash val="solid"/></a:ln>'
        z.writestr('ppt/theme/theme1.xml',xml(f'<a:theme xmlns:a="{A}" name="Writing Studio"><a:themeElements><a:clrScheme name="Writing">{color_xml}</a:clrScheme><a:fontScheme name="Writing"><a:majorFont><a:latin typeface="Aptos"/><a:ea typeface="Microsoft YaHei"/><a:cs typeface=""/></a:majorFont><a:minorFont><a:latin typeface="Aptos"/><a:ea typeface="Microsoft YaHei"/><a:cs typeface=""/></a:minorFont></a:fontScheme><a:fmtScheme name="Writing"><a:fillStyleLst>{fills*3}</a:fillStyleLst><a:lnStyleLst>{line*3}</a:lnStyleLst><a:effectStyleLst><a:effectStyle><a:effectLst/></a:effectStyle><a:effectStyle><a:effectLst/></a:effectStyle><a:effectStyle><a:effectLst/></a:effectStyle></a:effectStyleLst><a:bgFillStyleLst>{fills*3}</a:bgFillStyleLst></a:fmtScheme></a:themeElements></a:theme>'))
        for i,slide in enumerate(slides,1):
            title='\n'.join(slide['title'][j:j+24] for j in range(0,len(slide['title']),24))
            content=box(2,title,650000,600000,10800000,1550000,2400 if len(slide['title'])>72 else 3200,'172D39')+box(3,slide['body'],650000,2350000,10800000,3650000,2100,'234553')+box(4,f'论文写作 · 教师讲评     {i} / {len(slides)}',650000,6350000,10800000,300000,1100,'5D8093')
            z.writestr(f'ppt/slides/slide{i}.xml',xml(f'<p:sld xmlns:p="{P}" xmlns:a="{A}" xmlns:r="{R}"><p:cSld><p:bg><p:bgPr><a:solidFill><a:srgbClr val="F4F7F8"/></a:solidFill><a:effectLst/></p:bgPr></p:bg><p:spTree>{GROUP}{content}</p:spTree></p:cSld><p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr></p:sld>'))
            z.writestr(f'ppt/slides/_rels/slide{i}.xml.rels',relationships([(1,'slideLayout','../slideLayouts/slideLayout1.xml')]))
    return output.getvalue()
