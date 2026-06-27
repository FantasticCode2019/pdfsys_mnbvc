#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
分析PDF每页中不同种类文字的个数
支持中文、英文、数字、标点符号、特殊字符等分类统计
适配格式：JSONL中text字段为数组，每个元素代表一页内容
"""

import json
import re
from typing import Dict, List, Tuple
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

class TextTypeAnalyzer:
    """文本类型分析器：负责单字符分类、单页分析、整PDF分析"""
    
    def __init__(self):
        # 定义文字类型正则（覆盖中文、英文、数字等核心类型）
        self.patterns = {
            'chinese': re.compile(r'[\u4e00-\u9fff]'),           # 中文字符（含繁体）
            'english_letters': re.compile(r'[a-zA-Z]'),          # 英文字母（大小写）
            'digits': re.compile(r'[0-9]'),                      # 数字
            'whitespace': re.compile(r'\s'),                     # 空白字符（空格/换行/制表符）
            'punctuation': re.compile(r'[^\u4e00-\u9fff\w\s]'),  # 标点符号（非中文/单词/空白）
        }
        # 用于文档类型检测的预编译正则
        self.chinese_pattern = re.compile(r'[\u4e00-\u9fff]')
        self.english_pattern = re.compile(r'[a-zA-Z]')
    
    def categorize_character(self, char: str) -> str:
        """对单个字符分类，返回字符类型（如'chinese'、'digits'）"""
        if self.patterns['chinese'].match(char):
            return 'chinese'
        elif self.patterns['english_letters'].match(char):
            return 'english_letters'
        elif self.patterns['digits'].match(char):
            return 'digits'
        elif self.patterns['whitespace'].match(char):
            return 'whitespace'
        else:
            return 'punctuation'  # 剩余的都归类为标点符号
    
    def analyze_text(self, text: str) -> Dict[str, int]:
        """分析单页文本中各类字符的数量，返回统计字典"""
        counts = defaultdict(int)
        # 遍历文本中每个字符（处理空文本避免循环异常）
        for char in text.strip() if text else "":
            char_type = self.categorize_character(char)
            counts[char_type] += 1
        return dict(counts)
    
    def count_unique_chinese_chars(self, text: str) -> int:
        """统计单页中唯一中文字符的种类数（去重）"""
        chinese_chars = set()
        for char in text.strip() if text else "":
            if self.patterns['chinese'].match(char):
                chinese_chars.add(char)
        return len(chinese_chars)
    
    def count_unique_english_words(self, text: str) -> int:
        """统计单页中唯一英文单词的种类数（去重，仅保留长度≥2的单词）"""
        english_words = set()
        # 提取英文单词（忽略大小写，匹配连续字母）
        words = re.findall(r'\b[a-zA-Z]+\b', text.lower() if text else "")
        for word in words:
            if len(word) >= 2:  # 过滤短词（如"I"、"a"）
                english_words.add(word)
        return len(english_words)
    
    def detect_document_type(self, text: str) -> str:
        """根据中英文数量判断文档类型：中文(chinese)/英文(english)/混合(mixed)"""
        if not text:
            return 'unknown'  # 空文本返回未知类型
        chinese_count = len(self.chinese_pattern.findall(text))
        english_count = len(self.english_pattern.findall(text))

        if chinese_count > english_count:
            return 'chinese'
        elif english_count > chinese_count:
            return 'english'
        else:
            return 'mixed'
    
    def analyze_page(self, page_text: str, page_num: int) -> Dict[str, int]:
        """分析单页文本，返回包含页号、字符统计、多样性的完整结果"""
        # 基础字符统计
        char_stats = self.analyze_text(page_text)
        # 补充多样性指标（唯一中文字符、唯一英文单词）
        char_stats['unique_chinese_chars'] = self.count_unique_chinese_chars(page_text)
        char_stats['unique_english_words'] = self.count_unique_english_words(page_text)
        # 补充页号（与PDF实际页号一致，从1开始）
        char_stats['page_number'] = page_num
        # 补充单页文档类型
        char_stats['page_doc_type'] = self.detect_document_type(page_text)
        return char_stats
    
    def analyze_pdf(self, pdf_data: Dict) -> Tuple[str, List[Dict[str, int]]]:
        """分析整PDF：提取file_path，逐页解析text数组，返回全局结果"""
        # 获取PDF路径（默认"Unknown_Path"避免KeyError）
        file_path = pdf_data.get('file_path', 'Unknown_Path')
        # 获取text数组（默认空数组，兼容字段缺失场景）
        text_pages = pdf_data.get('text', [])
        
        page_analyses = []
        all_text = ""  # 拼接所有页文本，用于判断全局文档类型
        
        # 遍历text数组（页号从1开始，匹配PDF实际页号）
        for page_idx, page_text in enumerate(text_pages, 1):
            # 确保page_text是字符串（兼容非字符串类型数据）
            if isinstance(page_text, str):
                page_result = self.analyze_page(page_text, page_idx)
                page_analyses.append(page_result)
                # 拼接文本（保留页间分隔，避免字符粘连）
                all_text += page_text + "\n"
        
        # 为所有页补充全局文档类型（避免单页判断偏差）
        if page_analyses and all_text.strip():
            overall_doc_type = self.detect_document_type(all_text)
            for page in page_analyses:
                page['overall_doc_type'] = overall_doc_type
        
        return file_path, page_analyses

# 全局分析器实例（避免重复创建）
_global_analyzer = None

def get_analyzer():
    """获取全局分析器实例（线程安全的单例模式）"""
    global _global_analyzer
    if _global_analyzer is None:
        _global_analyzer = TextTypeAnalyzer()
    return _global_analyzer

def process_single_line(line_data):
    """处理单行JSONL数据：解析JSON、调用分析器、返回结果/错误信息"""
    line_num, line = line_data
    analyzer = get_analyzer()  # 使用全局分析器实例

    try:
        # 解析JSON（去除前后空白，避免格式错误）
        pdf_data = json.loads(line.strip())
        # 分析PDF数据
        file_path, page_analyses = analyzer.analyze_pdf(pdf_data)

        # 构建结果字典（包含文件信息、总页数、逐页统计、全局汇总）
        result = {
            'file_path': file_path,
            'total_pages': len(page_analyses),  # 总页数=text数组长度（非空页）
            'pages': page_analyses,            # 逐页统计结果
            'summary': calculate_pdf_summary(page_analyses)  # 全局汇总统计
        }
        return line_num, result, None  # 无错误时返回None

    except json.JSONDecodeError as e:
        # JSON解析错误（截取前50字符避免信息过长）
        return line_num, None, f"JSON解析错误: {str(e)[:50]}..."
    except Exception as e:
        # 其他未知错误（如字段异常、数据类型错误）
        return line_num, None, f"处理错误: {str(e)[:50]}..."

def calculate_pdf_summary(page_analyses: List[Dict[str, int]]) -> Dict[str, int]:
    """计算整PDF的全局统计：累加所有页的数值型字段（忽略字符串字段）"""
    summary = defaultdict(int)
    for page in page_analyses:
        for key, value in page.items():
            # 仅累加数值类型（跳过页号、文档类型等字符串字段）
            if key not in ['page_number', 'page_doc_type', 'overall_doc_type'] and isinstance(value, (int, float)):
                summary[key] += value
    return dict(summary)

def analyze_jsonl_file(
    input_file: str = "result.jsonl",  # 默认读取当前目录下的合并文件
    output_file: str = "text_analysis_results.json",
    max_records: int = None,  # 限制处理记录数（None=全部）
    num_threads: int = 4,     # 线程数（默认4，可根据CPU核心调整）
    batch_size: int = 1000    # 批处理大小（避免内存过载）
) -> List[Dict]:
    """多线程分析JSONL文件：读取数据、分发任务、收集结果、保存输出"""
    import os

    # 线程数限制（避免创建过多线程）
    cpu_count = os.cpu_count() or 4
    if num_threads > cpu_count * 2:
        print(f"警告：线程数({num_threads})过高，建议不超过CPU核心数的2倍({cpu_count * 2})")
        num_threads = min(num_threads, cpu_count * 2)

    results = []  # 存储成功处理的结果
    errors = []   # 存储错误信息

    print(f"=== 开始分析JSONL文件 ===")
    print(f"输入文件: {input_file}")
    print(f"输出文件: {output_file}")
    print(f"线程数: {num_threads} (CPU核心数: {cpu_count})")
    print(f"批处理大小: {batch_size}")
    print(f"最大处理记录数: {'全部' if max_records is None else max_records}\n")

    # 第一步：分批读取JSONL文件（避免大文件一次性加载到内存）
    try:
        with open(input_file, 'r', encoding='utf-8') as f:
            processed_count = 0

            while True:
                # 分批读取
                batch_lines = []
                for _ in range(batch_size):
                    line = f.readline()
                    if not line:  # 文件结束
                        break
                    processed_count += 1
                    if line.strip():  # 跳过空行
                        batch_lines.append((processed_count, line))
                    # 限制最大处理记录数
                    if max_records and processed_count >= max_records:
                        break

                if not batch_lines:  # 没有更多数据
                    break

                print(f"处理批次：第{processed_count-len(batch_lines)+1}-{processed_count}行（共{len(batch_lines)}行）")

                # 第二步：多线程处理当前批次
                with ThreadPoolExecutor(max_workers=num_threads) as executor:
                    # 提交当前批次的任务
                    future_to_line = {
                        executor.submit(process_single_line, line_data): line_data[0]
                        for line_data in batch_lines
                    }

                    # 处理完成的任务
                    batch_results = []
                    batch_errors = []

                    for future in as_completed(future_to_line):
                        line_num, result, error = future.result()

                        if error:
                            batch_errors.append(f"第{line_num}行: {error}")
                        else:
                            batch_results.append(result)

                    # 合并批次结果
                    results.extend(batch_results)
                    errors.extend(batch_errors)

                    print(f"批次完成：成功{len(batch_results)}个，错误{len(batch_errors)}个")

                # 检查是否达到最大记录数
                if max_records and processed_count >= max_records:
                    break

    except FileNotFoundError:
        print(f"错误：输入文件 {input_file} 不存在（请确认合并后的文件在当前目录）")
        return []
    except Exception as e:
        print(f"错误：读取文件失败 - {str(e)}")
        return []

    # 第三步：打印处理总结
    print(f"\n=== 处理完成 ===")
    print(f"总处理行数: {processed_count}")
    print(f"成功分析数: {len(results)}")
    print(f"错误数: {len(errors)}")

    # 打印前10个错误（避免信息过载）
    if errors:
        print(f"\n前10个错误示例:")
        for err in errors[:10]:
            print(f"  {err}")
        if len(errors) > 10:
            print(f"  ... 还有 {len(errors)-10} 个错误未显示")

    # 第四步：保存结果到JSON文件（支持中文显示）
    if results:
        try:
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(results, f, ensure_ascii=False, indent=2)
            print(f"\n结果已保存到: {output_file}")
        except Exception as e:
            print(f"\n错误：保存结果失败 - {str(e)}")

    return results

def print_statistics(results: List[Dict], top_n: int = 5):
    """打印全局统计信息：PDF数量、总页数、字符分布、最大PDF等"""
    if not results:
        print("\n=== 全局统计 ===")
        print("无有效分析结果可统计")
        return
    
    print("\n=== 全局统计信息 ===")
    # 基础统计：PDF总数、总页数
    total_pdfs = len(results)
    total_pages = sum(r['total_pages'] for r in results)
    print(f"1. 分析PDF总数: {total_pdfs}")
    print(f"2. 分析总页数: {total_pages}")
    
    # 页数最多的PDF（提取文件名避免路径过长）
    max_pages_pdf = max(results, key=lambda x: x['total_pages'])
    pdf_filename = max_pages_pdf['file_path'].split('/')[-1]
    print(f"3. 页数最多的PDF: {pdf_filename} ({max_pages_pdf['total_pages']}页)")
    
    # 字符类型全局分布（累加所有PDF的summary）
    global_char_counts = defaultdict(int)
    for result in results:
        summary = result['summary']
        for char_type, count in summary.items():
            global_char_counts[char_type] += count
    
    print(f"\n4. 字符类型全局分布（总数量）:")
    # 按字符数量降序排列，格式化千位分隔符
    sorted_char_types = sorted(global_char_counts.items(), key=lambda x: x[1], reverse=True)
    for char_type, count in sorted_char_types:
        print(f"   - {char_type}: {count:,}")
    
    # 总字符数最多的前N个PDF
    print(f"\n5. 总字符数最多的前{top_n}个PDF:")
    # 按总字符数排序（总字符数=所有字符类型数量之和）
    sorted_by_total = sorted(
        results,
        key=lambda x: sum(x['summary'].values()),
        reverse=True
    )
    for i, res in enumerate(sorted_by_total[:top_n], 1):
        total_chars = sum(res['summary'].values())
        filename = res['file_path'].split('/')[-1]
        print(f"   {i}. {filename}: {total_chars:,}字符 ({res['total_pages']}页)")

def analyze_text_diversity(results: List[Dict], threshold: int = 50):
    """分析文本多样性：统计超过阈值的高多样性页面（按文档类型区分）"""
    if not results:
        print("\n=== 文本多样性分析 ===")
        print("无有效分析结果可分析")
        return
    
    print(f"\n=== 文本多样性分析（阈值: {threshold}）===")
    high_diversity = []  # 高多样性页面列表
    total_pages = 0      # 总页数
    doc_type_count = defaultdict(int)  # 文档类型分布
    
    for res in results:
        file_path = res['file_path']
        filename = file_path.split('/')[-1]
        pages = res['pages']
        
        # 统计文档类型（按全局类型）
        if pages:
            overall_type = pages[0].get('overall_doc_type', 'unknown')
            doc_type_count[overall_type] += 1
        
        # 逐页判断高多样性
        for page in pages:
            total_pages += 1
            page_num = page['page_number']
            unique_chinese = page['unique_chinese_chars']
            unique_english = page['unique_english_words']
            overall_type = page.get('overall_doc_type', 'unknown')
            
            # 按文档类型判断阈值（中文看唯一中文字符，英文看唯一英文单词）
            if overall_type == 'chinese' and unique_chinese > threshold:
                high_diversity.append({
                    'pdf': filename,
                    'page': page_num,
                    'type': 'unique_chinese_chars',
                    'count': unique_chinese
                })
            elif overall_type == 'english' and unique_english > threshold:
                high_diversity.append({
                    'pdf': filename,
                    'page': page_num,
                    'type': 'unique_english_words',
                    'count': unique_english
                })
            elif overall_type == 'mixed':
                # 混合文档取两者最大值
                if max(unique_chinese, unique_english) > threshold:
                    diversity_type = 'unique_chinese_chars' if unique_chinese >= unique_english else 'unique_english_words'
                    high_diversity.append({
                        'pdf': filename,
                        'page': page_num,
                        'type': diversity_type,
                        'count': max(unique_chinese, unique_english)
                    })
    
    # 计算占比
    diversity_ratio = len(high_diversity) / total_pages if total_pages > 0 else 0
    
    # 输出核心统计
    print(f"1. 总页数: {total_pages}")
    print(f"2. 文档类型分布: 中文{doc_type_count.get('chinese',0)}个 | 英文{doc_type_count.get('english',0)}个 | 混合{doc_type_count.get('mixed',0)}个 | 未知{doc_type_count.get('unknown',0)}个")
    print(f"3. 高多样性页面数: {len(high_diversity)} (占比: {diversity_ratio:.2%})")
    
    # 按文档类型拆分高多样性页面
    chinese_high = [p for p in high_diversity if p['type'] == 'unique_chinese_chars']
    english_high = [p for p in high_diversity if p['type'] == 'unique_english_words']
    print(f"\n4. 高多样性页面类型分布:")
    print(f"   - 中文高多样性（唯一中文字符超{threshold}）: {len(chinese_high)}页")
    print(f"   - 英文高多样性（唯一英文单词超{threshold}）: {len(english_high)}页")
    
    # 显示前10个高多样性页面示例
    if high_diversity:
        print(f"\n5. 前10个高多样性页面示例:")
        for i, page in enumerate(high_diversity[:10], 1):
            print(f"   {i}. {page['pdf']}（第{page['page']}页）: {page['type']}={page['count']}")
    
    return {
        'total_pages': total_pages,
        'high_diversity_count': len(high_diversity),
        'diversity_ratio': diversity_ratio,
        'doc_type_distribution': dict(doc_type_count),
        'samples': high_diversity[:10]
    }

def analyze_high_diversity_ratio(results: List[Dict], chinese_threshold: int = 120, english_threshold: int = 100):
    """分析高多样性页面占比（按文档类型设置不同阈值，更贴合实际场景）"""
    if not results:
        print("\n=== 高多样性占比分析 ===")
        print("无有效分析结果可分析")
        return
    
    print(f"\n=== 高多样性页面占比分析（中文阈值:{chinese_threshold}, 英文阈值:{english_threshold}）===")
    # 基础计数变量
    total_pages = 0
    chinese_pages = 0  # 中文文档总页数
    english_pages = 0  # 英文文档总页数
    mixed_pages = 0    # 混合文档总页数
    
    # 高多样性计数
    high_chinese = 0   # 中文文档中中文字符超阈值
    high_english = 0   # 英文文档中英文单词超阈值
    high_mixed = 0     # 混合文档中任一类型超阈值
    
    # 统计涉及高多样性的文件
    high_diversity_files = set()
    
    for res in results:
        file_path = res['file_path']
        filename = file_path.split('/')[-1]
        pages = res['pages']
        
        for page in pages:
            total_pages += 1
            doc_type = page.get('overall_doc_type', 'unknown')
            unique_chinese = page['unique_chinese_chars']
            unique_english = page['unique_english_words']
            
            # 按文档类型分类计数
            if doc_type == 'chinese':
                chinese_pages += 1
                if unique_chinese > chinese_threshold:
                    high_chinese += 1
                    high_diversity_files.add(filename)
            elif doc_type == 'english':
                english_pages += 1
                if unique_english > english_threshold:
                    high_english += 1
                    high_diversity_files.add(filename)
            elif doc_type == 'mixed':
                mixed_pages += 1
                if unique_chinese > chinese_threshold or unique_english > english_threshold:
                    high_mixed += 1
                    high_diversity_files.add(filename)
    
    # 计算各类占比
    chinese_ratio = high_chinese / chinese_pages if chinese_pages > 0 else 0
    english_ratio = high_english / english_pages if english_pages > 0 else 0
    mixed_ratio = high_mixed / mixed_pages if mixed_pages > 0 else 0
    
    # 输出统计结果
    print(f"1. 总页数: {total_pages:,}")
    print(f"   - 中文文档页数: {chinese_pages:,}")
    print(f"   - 英文文档页数: {english_pages:,}")
    print(f"   - 混合文档页数: {mixed_pages:,}")
    
    print(f"\n2. 高多样性页面统计:")
    print(f"   - 中文文档（中文字符超{chinese_threshold}）: {high_chinese:,}页 (占比: {chinese_ratio:.2%})")
    print(f"   - 英文文档（英文单词超{english_threshold}）: {high_english:,}页 (占比: {english_ratio:.2%})")
    print(f"   - 混合文档（任一类型超阈值）: {high_mixed:,}页 (占比: {mixed_ratio:.2%})")
    
    print(f"\n3. 涉及高多样性的文件数: {len(high_diversity_files)}")
    
    return {
        'page_distribution': {
            'total': total_pages,
            'chinese': chinese_pages,
            'english': english_pages,
            'mixed': mixed_pages
        },
        'high_diversity_counts': {
            'chinese': high_chinese,
            'english': high_english,
            'mixed': high_mixed
        },
        'ratios': {
            'chinese': chinese_ratio,
            'english': english_ratio,
            'mixed': mixed_ratio
        },
        'high_diversity_files_count': len(high_diversity_files)
    }

def analyze_saved_results(json_file: str, chinese_threshold: int = 120, english_threshold: int = 100):
    """单独分析已保存的结果文件（无需重新处理JSONL）"""
    print(f"\n=== 分析已保存结果文件 ===")
    print(f"目标文件: {json_file}")
    
    try:
        # 读取已保存的结果
        with open(json_file, 'r', encoding='utf-8') as f:
            results = json.load(f)
        
        print(f"成功读取: {len(results)}个PDF的分析结果")
        
        # 执行高多样性占比分析
        ratio_stats = analyze_high_diversity_ratio(results, chinese_threshold, english_threshold)
        # 执行文本多样性分析（默认阈值50）
        analyze_text_diversity(results)
        
        return ratio_stats
        
    except FileNotFoundError:
        print(f"错误：文件 {json_file} 不存在")
        return None
    except json.JSONDecodeError as e:
        print(f"错误：JSON格式错误 - {str(e)[:50]}...")
        return None
    except Exception as e:
        print(f"错误：分析失败 - {str(e)[:50]}...")
        return None

def show_sample_analysis(results: List[Dict], pdf_index: int = 0, page_index: int = 0):
    """展示单个PDF的详细分析样本（便于验证数据正确性）"""
    if not results or pdf_index >= len(results):
        print("\n=== 样本分析 ===")
        print("无有效样本可展示")
        return
    
    sample = results[pdf_index]
    # 确保页码有效
    if page_index >= len(sample['pages']):
        page_index = 0  # 页码无效时默认显示第1页
    
    page = sample['pages'][page_index]
    pdf_filename = sample['file_path'].split('/')[-1]
    overall_type = page.get('overall_doc_type', 'unknown')
    
    print(f"\n=== 样本分析: {pdf_filename} ===")
    print(f"全局文档类型: {overall_type} | 总页数: {sample['total_pages']} | 分析页: 第{page['page_number']}页")
    
    # 显示页面核心统计
    print(f"\n页面核心统计:")
    print(f"   - 唯一中文字符: {page['unique_chinese_chars']}种")
    print(f"   - 唯一英文单词: {page['unique_english_words']}种")
    print(f"   - 页面文档类型: {page['page_doc_type']}")
    
    # 显示页面字符分布
    print(f"\n页面字符分布:")
    char_fields = ['chinese', 'english_letters', 'digits', 'punctuation', 'whitespace', 'special_chars']
    for field in char_fields:
        print(f"   - {field}: {page.get(field, 0)}个")
    
    # 显示全局汇总（当前PDF）
    print(f"\n当前PDF全局汇总:")
    for field, count in sample['summary'].items():
        print(f"   - {field}: {count:,}")

if __name__ == "__main__":
    import sys
    
    # 配置默认参数（匹配合并后的JSONL文件）
    input_file = "result.jsonl"       # 输入：当前目录下的合并文件
    output_file = "text_analysis_results.json"  # 输出：分析结果文件
    num_threads = 4                   # 默认线程数（可通过命令行调整）
    
    # 解析命令行参数
    # 支持两种模式：1. 处理JSONL文件 2. 分析已保存结果
    if len(sys.argv) > 1:
        # 模式1：分析已保存结果（命令：python script.py analyze [中文阈值] [英文阈值]）
        if sys.argv[1] == "analyze":
            chinese_thresh = int(sys.argv[2]) if len(sys.argv) > 2 else 120
            english_thresh = int(sys.argv[3]) if len(sys.argv) > 3 else 100
            analyze_saved_results(output_file, chinese_thresh, english_thresh)
            sys.exit(0)
        # 模式2：调整线程数（命令：python script.py 8）
        else:
            try:
                num_threads = int(sys.argv[1])
                print(f"已设置线程数: {num_threads}（建议不超过CPU核心数）")
            except ValueError:
                print(f"线程数参数无效（{sys.argv[1]}），使用默认值{num_threads}")
    
    # 主流程：处理JSONL文件并执行完整分析
    print("=== PDF文本类型分析主流程 ===")
    print(f"输入文件: {input_file} | 输出文件: {output_file} | 线程数: {num_threads}")
    
    # 执行JSONL分析
    results = analyze_jsonl_file(
        input_file=input_file,
        output_file=output_file,
        max_records=None,  # 处理全部记录
        num_threads=num_threads
    )
    
    # 执行后续分析（仅当有有效结果时）
    if results:
        print_statistics(results, top_n=5)          # 全局统计
        analyze_text_diversity(results, threshold=50)  # 文本多样性
        analyze_high_diversity_ratio(results)       # 高多样性占比
        show_sample_analysis(results)               # 样本展示
    
    print(f"\n=== 分析流程全部完成 ===")
    print(f"详细结果文件: {output_file}")
    print(f"重新分析结果命令: python {sys.argv[0]} analyze [中文阈值] [英文阈值]")