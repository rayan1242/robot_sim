"""Export the engineering report to PDF with embedded charts and wrapped tables."""
import argparse
from html import escape
from pathlib import Path
import re
import xml.etree.ElementTree as ET

import markdown
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, Preformatted
from reportlab.graphics.shapes import Drawing, Rect, String, Line, Polygon


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,default=Path('docs/project_report.md'))
    parser.add_argument('--output',type=Path,default=Path('docs/project_report.pdf'))
    parser.add_argument('--title',default='Camera-only perception: project engineering report')
    parser.add_argument('--footer',default='Camera-only perception | Engineering report | November 1, 2026')
    args=parser.parse_args()
    for name,file in [('Body','arial.ttf'),('BodyBold','arialbd.ttf'),('Mono','consola.ttf')]:
        pdfmetrics.registerFont(TTFont(name,str(Path('C:/Windows/Fonts')/file)))
    pdfmetrics.registerFontFamily('Body',normal='Body',bold='BodyBold',italic='Body',boldItalic='BodyBold')
    styles=getSampleStyleSheet()
    for name in ['Normal','BodyText','Title','Heading1','Heading2','Heading3']:
        styles[name].fontName='BodyBold' if name.startswith('Heading') or name=='Title' else 'Body'
    styles['BodyText'].fontSize=9.5;styles['BodyText'].leading=14;styles['BodyText'].spaceAfter=7
    styles['Title'].fontSize=24;styles['Title'].leading=29;styles['Title'].spaceAfter=14
    styles['Heading1'].fontSize=16;styles['Heading1'].leading=21
    styles['Heading2'].fontSize=12;styles['Heading2'].leading=16
    styles['Heading3'].fontSize=10.5;styles['Heading3'].leading=14
    for name in ['Title','Heading1','Heading2','Heading3']:
        styles[name].keepWithNext=True
    styles.add(ParagraphStyle('Cell',fontName='Body',fontSize=8,leading=11))
    styles.add(ParagraphStyle('Quote',parent=styles['BodyText'],leftIndent=15,borderPadding=8,
                              borderColor=colors.HexColor('#0d9488'),borderWidth=1,spaceAfter=12))
    styles.add(ParagraphStyle('Caption',parent=styles['BodyText'],fontSize=8,leading=11,textColor=colors.HexColor('#475569'),alignment=TA_CENTER))
    width=7.1*inch
    doc=SimpleDocTemplate(str(args.output),pagesize=(8.5*inch,11*inch),rightMargin=.7*inch,leftMargin=.7*inch,
        topMargin=.65*inch,bottomMargin=.65*inch,title=args.title,author='Rayyan')
    root=ET.fromstring('<report>'+markdown.markdown(args.source.read_text(encoding='utf-8'),extensions=['tables','fenced_code'])+'</report>')
    story=[];images=[]

    def inline(node):
        text=escape(node.text or '')
        for child in node:
            value=inline(child)
            if child.tag in ('strong','b'):value='<b>'+value+'</b>'
            elif child.tag in ('em','i'):value='<i>'+value+'</i>'
            elif child.tag=='code':value='<font face="Mono">'+value+'</font>'
            elif child.tag=='a':
                target=child.get('href','')
                if not target.startswith(('http:','https:','#')):target=(args.source.parent/target).resolve().as_uri()
                value='<a href="'+escape(target,quote=True)+'" color="#0f766e">'+value+'</a>'
            elif child.tag=='br':value='<br/>'
            text+=value+escape(child.tail or '')
        return text

    def diagram():
        labels=['USB webcam: DirectShow 640 x 480','Latest-frame capture and monotonic timestamps',
            'Persistent WSL SLAM over lossless BGR pipe','Depth Anything V2 Small: CPU 224 x 168',
            'Candidate selection across cached anchors','Positive-scale alignment and quality gates',
            'Geometry-diverse window: up to 4 accepted views','Cross-view validation and current-pose rebuilding',
            'FastAPI / WebSocket / local dashboard and replay']
        drawing=Drawing(width,370);boxw=width-50
        for i,label in enumerate(labels):
            y=335-i*40
            drawing.add(Rect(25,y,boxw,28,rx=5,ry=5,fillColor=colors.HexColor('#f0fdfa'),strokeColor=colors.HexColor('#0f766e')))
            drawing.add(String(width/2,y+10,label,fontName='Body',fontSize=8.5,textAnchor='middle'))
            if i<len(labels)-1:
                drawing.add(Line(width/2,y,width/2,y-9,strokeColor=colors.HexColor('#64748b')))
                drawing.add(Polygon([width/2-3,y-6,width/2+3,y-6,width/2,y-11],fillColor=colors.HexColor('#64748b'),strokeColor=None))
        return drawing

    def add(node):
        if node.tag in ('h1','h2','h3','h4'):
            name={'h1':'Title','h2':'Heading1','h3':'Heading2','h4':'Heading3'}[node.tag]
            story.append(Paragraph(inline(node),styles[name]))
        elif node.tag=='p':
            imgs=list(node.iter('img'))
            if imgs:
                for img in imgs:
                    path=(args.source.parent/img.get('src')).resolve()
                    if not path.exists():raise FileNotFoundError(path)
                    image=Image(str(path));scale=min(width/image.imageWidth,330/image.imageHeight)
                    image.drawWidth=image.imageWidth*scale;image.drawHeight=image.imageHeight*scale
                    story.extend([image,Paragraph(escape(img.get('alt','')),styles['Caption']),Spacer(1,8)])
                    images.append(str(path))
            else:story.append(Paragraph(inline(node),styles['BodyText']))
        elif node.tag=='table':
            rows=[[Paragraph(inline(cell),styles['Cell']) for cell in tr] for tr in node.iter('tr')]
            n=max(map(len,rows));table=Table(rows,colWidths=[width/n]*n,repeatRows=1,hAlign='LEFT')
            table.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#e2e8f0')),
                ('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,colors.HexColor('#f8fafc')]),
                ('VALIGN',(0,0),(-1,-1),'TOP'),('GRID',(0,0),(-1,-1),.3,colors.HexColor('#cbd5e1')),
                ('LEFTPADDING',(0,0),(-1,-1),6),('RIGHTPADDING',(0,0),(-1,-1),6),
                ('TOPPADDING',(0,0),(-1,-1),6),('BOTTOMPADDING',(0,0),(-1,-1),6)]))
            story.extend([table,Spacer(1,10)])
        elif node.tag in ('ol','ul'):
            for i,li in enumerate(node,1):
                story.append(Paragraph(inline(li),styles['BodyText'],bulletText=f'{i}.' if node.tag=='ol' else '•'))
        elif node.tag=='blockquote':
            for p in node:story.append(Paragraph(inline(p),styles['Quote']))
        elif node.tag=='pre':
            code=node.find('code')
            if code is not None and 'mermaid' in code.get('class',''):
                story.extend([diagram(),Spacer(1,8)])
            else:
                style=ParagraphStyle('Code',fontName='Mono',fontSize=7,leading=10,spaceAfter=9)
                story.append(Preformatted(''.join(node.itertext()),style,maxLineLength=100))
        else:
            for child in node:add(child)

    for node in root:add(node)
    def footer(canvas,document):
        canvas.setFont('Body',8);canvas.setFillColor(colors.HexColor('#64748b'))
        canvas.drawString(.7*inch,.34*inch,args.footer)
        canvas.drawRightString(7.8*inch,.34*inch,str(document.page))
    doc.build(story,onFirstPage=footer,onLaterPages=footer)
    print(f'Saved {args.output}; embedded {len(images)} charts')


if __name__=='__main__':main()
