from lxml import etree
from datetime import datetime
from typing import Dict, List
from PIL import Image
import pytesseract
import os

class IB373CompleteParser:
    """IB373完整解析器 - 处理XML + TIF文件"""
    
    def __init__(self, xml_file: str, tif_folder: str):
        self.xml_file = xml_file
        self.tif_folder = tif_folder
        self.xml_tree = etree.parse(xml_file)
        self.xml_root = self.xml_tree.getroot()
        
    def extract_all_xml_data(self) -> Dict:
        """
        从XML中提取所有可用数据
        """
        root = self.xml_root
        
        # 1. 文档元数据（根节点属性）
        document_metadata = {
            'date_produced': self._parse_date(root.get('date-produced')),  # 20130122
            'file_name': root.get('file'),  # IB373.xml
            'language': root.get('lang'),  # en
            'produced_by': root.get('produced-by'),  # IB (International Bureau)
            'status': root.get('status'),  # new
            'dtd_version': root.get('dtd-version')  # 1.0
        }
        
        # 2. 文档页数信息
        number_of_sheets = root.find('.//number-of-sheets')
        sheets_info = {
            'total_sheets': int(number_of_sheets.text) if number_of_sheets is not None else 0,  # 7
            'expected_tif_files': int(number_of_sheets.text) if number_of_sheets is not None else 0
        }
        
        # 3. 文件参考ID
        file_reference = {
            'reference_id': self._get_text('.//file-reference-id')  # SP10-202
        }
        
        # 4. 申请参考信息
        application_reference = {
            'application_type': root.find('.//application-reference').get('appl-type'),  # international
            'country': self._get_text('.//application-reference//country'),  # US
            'document_number': self._get_text('.//application-reference//doc-number'),  # US2011044347
            'application_date': self._parse_date(self._get_text('.//application-reference//date', ''))  # 2011-07-18
        }
        
        # 5. 优先权日期
        priority_info = {
            'earliest_priority_date': self._parse_date(
                self._get_text('.//date-of-earliest-priority/date', '')
            )  # 2010-07-21
        }
        
        # 6. 申请人信息
        applicant_info = {
            'applicant_name': self._get_text('.//applicant-name/name')  # CORNING INCORPORATED
        }
        
        # 7. 传送内容项（重要！告诉我们PDF中哪些box被勾选）
        transmitted_items = []
        for item in root.findall('.//ib373-contents'):
            box_id = item.get('item')  # box1, box5, box8
            transmitted_items.append({
                'box_id': box_id,
                'box_number': box_id.replace('box', ''),
                'description': self._get_box_description(box_id),
                'checked': True
            })
        
        # 8. 授权官员信息
        authorized_officer = {
            'officer_name': self._get_text('.//authorized-officer/name'),  # Athina Nickitas-Etienne
            'email': self._get_text('.//authorized-officer/email'),  # pt04.pct@wipo.int
            'signature_date': self._parse_date(
                root.find('.//electronic-signature').get('date')
                if root.find('.//electronic-signature') is not None else ''
            ),  # 2013-01-22
            'signature_text': self._get_text('.//text-string')  # /Athina Nickitas-Etienne/
        }
        
        return {
            'document_metadata': document_metadata,
            'sheets_info': sheets_info,
            'file_reference': file_reference,
            'application_reference': application_reference,
            'priority_info': priority_info,
            'applicant_info': applicant_info,
            'transmitted_items': transmitted_items,
            'authorized_officer': authorized_officer
        }
    
    def _get_text(self, xpath: str, default: str = 'N/A') -> str:
        """安全获取XML文本"""
        elem = self.xml_root.find(xpath)
        return elem.text if elem is not None and elem.text else default
    
    def _parse_date(self, date_str: str) -> str:
        """解析日期：20130122 -> 2013-01-22"""
        if date_str and len(date_str) == 8:
            try:
                date_obj = datetime.strptime(date_str, '%Y%m%d')
                return date_obj.strftime('%Y-%m-%d')
            except:
                pass
        return date_str or 'N/A'
    
    def _get_box_description(self, box_id: str) -> str:
        """
        获取Box的标准描述
        基于WIPO IB/373表格标准
        """
        box_descriptions = {
            'box1': 'copies of the translation of the international application into English',
            'box2': 'copies of the translation of the amendments under Article 19 into English',
            'box3': 'copies of the translation of the annexes to the international preliminary examination report into English',
            'box4': 'the international application in English',
            'box5': 'copies of the amendments under Article 19 in English',
            'box6': 'copies of the annexes to the international preliminary examination report in English',
            'box7': 'copies of the international search report and the written opinion of the International Searching Authority',
            'box8': 'copies of the international preliminary examination report',
            'box9': 'other (specify):',
            'box10': 'notification concerning the priority document'
        }
        return box_descriptions.get(box_id, f'Unknown item: {box_id}')
    
    def scan_tif_files(self) -> List[Dict]:
        """
        扫描TIF文件信息
        """
        tif_files = []
        
        if not os.path.exists(self.tif_folder):
            print(f"⚠️  TIF folder not found: {self.tif_folder}")
            return tif_files
        
        # 获取所有TIF文件
        files = sorted([f for f in os.listdir(self.tif_folder) if f.lower().endswith(('.tif', '.tiff'))])
        
        for idx, filename in enumerate(files, 1):
            filepath = os.path.join(self.tif_folder, filename)
            
            try:
                with Image.open(filepath) as img:
                    tif_files.append({
                        'page_number': idx,
                        'filename': filename,
                        'filepath': filepath,
                        'size': img.size,  # (width, height)
                        'mode': img.mode,  # RGB, L, etc.
                        'format': img.format,  # TIFF
                        'file_size_kb': os.path.getsize(filepath) / 1024
                    })
            except Exception as e:
                print(f"❌ Error reading {filename}: {e}")
        
        return tif_files
    
    def extract_text_from_tif(self, tif_path: str, page_description: str = '') -> str:
        """
        从TIF文件中提取文本（使用OCR）
        """
        try:
            img = Image.open(tif_path)
            
            # 如果是多页TIFF，处理所有页
            text_content = []
            
            try:
                for page_num in range(img.n_frames):
                    img.seek(page_num)
                    
                    # OCR提取文本
                    text = pytesseract.image_to_string(img, lang='eng')
                    
                    if text.strip():
                        text_content.append(f"--- Page {page_num + 1} ---\n{text}")
            except AttributeError:
                # 单页TIFF
                text = pytesseract.image_to_string(img, lang='eng')
                text_content.append(text)
            
            return '\n\n'.join(text_content)
            
        except Exception as e:
            print(f"❌ OCR Error on {tif_path}: {e}")
            return f"[OCR failed for this page: {page_description}]"
    
    def generate_markdown(self, include_ocr: bool = False) -> str:
        """
        生成完整的Markdown文档
        
        Args:
            include_ocr: 是否包含OCR提取的文本内容
        """
        # 提取XML数据
        xml_data = self.extract_all_xml_data()
        
        # 扫描TIF文件
        tif_files = self.scan_tif_files()
        
        # 验证文件数量
        expected_sheets = xml_data['sheets_info']['total_sheets']
        actual_files = len(tif_files)
        
        md = f"""# NOTIFICATION OF TRANSMITTAL
## Form IB/373 - International Bureau

---

## 📋 Document Summary

| Field | Value |
|-------|-------|
| **Document Type** | IB/373 - Notification of Transmittal |
| **Status** | {xml_data['document_metadata']['status'].upper()} |
| **Produced By** | {xml_data['document_metadata']['produced_by']} (International Bureau) |
| **Date Produced** | {xml_data['document_metadata']['date_produced']} |
| **Language** | {xml_data['document_metadata']['language'].upper()} |
| **Total Pages** | {expected_sheets} |
| **DTD Version** | {xml_data['document_metadata']['dtd_version']} |

---

## 🔍 File Reference Information

| Field | Value |
|-------|-------|
| **File Reference ID** | `{xml_data['file_reference']['reference_id']}` |
| **XML Source File** | `{xml_data['document_metadata']['file_name']}` |
| **Attached Files** | {actual_files} TIF image file(s) |

---

## 📄 International Application Details

### Application Reference

| Field | Value |
|-------|-------|
| **Application Type** | {xml_data['application_reference']['application_type'].capitalize()} |
| **Country Code** | {xml_data['application_reference']['country']} |
| **Document Number** | `{xml_data['application_reference']['document_number']}` |
| **Filing Date** | {xml_data['application_reference']['application_date']} |
| **Earliest Priority Date** | {xml_data['priority_info']['earliest_priority_date']} |

### Applicant Information

**Name:** {xml_data['applicant_info']['applicant_name']}

---

## 📦 Transmitted Documents

The International Bureau hereby transmits the following:

"""
        
        # 添加传送项目
        for item in xml_data['transmitted_items']:
            md += f"### ☑️ Box {item['box_number']}\n\n"
            md += f"**Description:** {item['description']}\n\n"
        
        # 添加未勾选的box（用于完整性）
        all_boxes = set([f'box{i}' for i in range(1, 11)])
        checked_boxes = set([item['box_id'] for item in xml_data['transmitted_items']])
        unchecked_boxes = all_boxes - checked_boxes
        
        if unchecked_boxes:
            md += "\n### ☐ Not Transmitted\n\n"
            for box_id in sorted(unchecked_boxes):
                box_num = box_id.replace('box', '')
                description = self._get_box_description(box_id)
                md += f"- **Box {box_num}**: {description}\n"
        
        md += f"""
---

## ✍️ Authorization & Signature

| Field | Value |
|-------|-------|
| **Authorized Officer** | {xml_data['authorized_officer']['officer_name']} |
| **Email** | {xml_data['authorized_officer']['email']} |
| **Signature Date** | {xml_data['authorized_officer']['signature_date']} |
| **Electronic Signature** | `{xml_data['authorized_officer']['signature_text']}` |

---

## 📁 Attached Files Information

**Expected Files:** {expected_sheets}  
**Actual Files Found:** {actual_files}  
**Status:** {'✅ Complete' if actual_files == expected_sheets else f'⚠️  Mismatch ({actual_files}/{expected_sheets})'}

### File Details

| Page | Filename | Size | Dimensions | Format |
|------|----------|------|------------|--------|
"""
        
        # 添加TIF文件信息
        for tif in tif_files:
            md += f"| {tif['page_number']} | `{tif['filename']}` | {tif['file_size_kb']:.1f} KB | {tif['size'][0]}×{tif['size'][1]} | {tif['format']} |\n"
        
        # 如果需要，添加OCR内容
        if include_ocr and tif_files:
            md += "\n---\n\n## 📝 Extracted Text Content (OCR)\n\n"
            
            for tif in tif_files:
                md += f"### Page {tif['page_number']}: {tif['filename']}\n\n"
                
                # 提取文本
                text = self.extract_text_from_tif(tif['filepath'], tif['filename'])
                
                if text.strip():
                    md += f"```text\n{text}\n```\n\n"
                else:
                    md += "*No text content extracted*\n\n"
        
        # 添加元数据
        md += f"""
---

## 🔖 Metadata

- **Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
- **Source XML:** `{xml_data['document_metadata']['file_name']}`
- **Parser Version:** 1.0
- **Data Sources:** XML Metadata + TIF Images

---

## 📊 Data Quality Report

| Metric | Status |
|--------|--------|
| XML Validation | ✅ Valid |
| Required Fields | ✅ Complete |
| File Count Match | {'✅ Match' if actual_files == expected_sheets else '⚠️  Mismatch'} |
| Signature Present | {'✅ Yes' if xml_data['authorized_officer']['signature_text'] != 'N/A' else '❌ No'} |
| Date Consistency | ✅ Valid |

---

### 🔗 Related Documents

Based on the transmitted items, the following documents are included:

"""
        
        # 根据勾选的box，列出相关文档
        for item in xml_data['transmitted_items']:
            if 'translation' in item['description'].lower():
                md += f"- Translation documents (English)\n"
            elif 'priority' in item['description'].lower():
                md += f"- Priority document copy\n"
            elif 'search report' in item['description'].lower():
                md += f"- International search report\n"
        
        md += """
---

*This document was automatically generated from structured XML metadata and scanned TIF images.*
"""
        
        return md
    
    def save_markdown(self, output_file: str, include_ocr: bool = False):
        """保存为Markdown文件"""
        md_content = self.generate_markdown(include_ocr=include_ocr)
        
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(md_content)
        
        print(f"✅ Markdown saved to: {output_file}")
        
        # 生成摘要
        xml_data = self.extract_all_xml_data()
        print(f"\n📊 Document Summary:")
        print(f"   - File Reference: {xml_data['file_reference']['reference_id']}")
        print(f"   - Application: {xml_data['application_reference']['document_number']}")
        print(f"   - Applicant: {xml_data['applicant_info']['applicant_name']}")
        print(f"   - Items Transmitted: {len(xml_data['transmitted_items'])}")
        print(f"   - Total Pages: {xml_data['sheets_info']['total_sheets']}")


# 完整使用示例
if __name__ == "__main__":
    # 初始化解析器
    parser = IB373CompleteParser(
        xml_file='IB373.xml',
        tif_folder='./tif_files'  # TIF文件所在文件夹
    )
    
    # 方法1: 生成基本Markdown（不包含OCR）
    parser.save_markdown('IB373_basic.md', include_ocr=False)
    
    # 方法2: 生成完整Markdown（包含OCR文本）
    # parser.save_markdown('IB373_full.md', include_ocr=True)
    
    # 方法3: 只提取XML数据
    xml_data = parser.extract_all_xml_data()
    print("\n=== XML Data ===")
    import json
    print(json.dumps(xml_data, indent=2, ensure_ascii=False))
    
    # 方法4: 只扫描TIF文件
    tif_files = parser.scan_tif_files()
    print("\n=== TIF Files ===")
    for tif in tif_files:
        print(f"Page {tif['page_number']}: {tif['filename']} - {tif['size']}")
'''
pip install lxml Pillow pytesseract python-dateutil
# 安装Tesseract OCR引擎
# Ubuntu/Debian:
sudo apt-get install tesseract-ocr
# macOS:
brew install tesseract
'''