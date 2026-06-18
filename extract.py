import pdfplumber
import pandas as pd
import re
from collections import Counter

def extract_words(pdf_path, page_start, page_end):
    rows = []
    pdf = pdfplumber.open(pdf_path)
    for page_num, page in enumerate(pdf.pages[page_start:page_end], start=page_start):
        for word in page.extract_words():
            rows.append({
                'page': page_num,
                'top': round(word['top']),
                'x0': word['x0'],
                'height': round(word['height'], 1),
                'text': word['text']
            })
    return pd.DataFrame(rows)

def build_lines(df):
    lines = df.groupby(['page', 'top']).agg(
        height=('height', 'first'),
        text=('text', ' '.join)
    ).reset_index()
    return lines.sort_values(['page', 'top']).reset_index(drop=True)

def classify_lines(lines_df):
    body = Counter(lines_df['height']).most_common(1)[0][0]
    section = body * 1.3
    chapter = body * 1.8

    def get_type(h):
        if h >= chapter:
            return 'chapter'
        elif h >= section:
            return 'section'
        else:
            return 'body'

    lines_df['type'] = lines_df['height'].apply(get_type)
    
    # merge consecutive same-height rows into one
    merged = []
    for _, row in lines_df.iterrows():
        if merged and round(merged[-1]['height'], 1) == round(row['height'], 1) and merged[-1]['page'] == row['page']:
            merged[-1]['text'] += ' ' + row['text']
        else:
            merged.append(row.to_dict())
    
    return pd.DataFrame(merged)


def build_nodes_and_chunks(lines_df):
    nodes = []
    chunks = []
    current_chapter_id = None
    current_section_id = None
    chunk_order = 0
    node_id = 0
    chapter_number = None

    for _, row in lines_df.iterrows():
        # detect "CHAPTER X" label — extract number but skip as node
        chapter_match = re.match(r'^CHAPTER\s+(\d+)$', row['text'].strip(), re.IGNORECASE)
        if chapter_match:
            chapter_number = chapter_match.group(1)
            continue

        if row['type'] == 'chapter':
            node_id += 1
            current_chapter_id = node_id
            current_section_id = None
            chunk_order = 0
            nodes.append({
                'id': node_id,
                'type': 'chapter',
                'depth': 0,
                'number': chapter_number or '',
                'title': row['text'],
                'page_start': row['page'],
                'parent_id': None
            })
            chapter_number = None

        elif row['type'] == 'section':
            node_id += 1
            current_section_id = node_id
            chunk_order = 0
            nodes.append({
                'id': node_id,
                'type': 'section',
                'depth': 1,
                'number': '',
                'title': row['text'],
                'page_start': row['page'],
                'parent_id': current_chapter_id
            })

        else:
            if row['height'] < 9.5:  # filter footers/headers
                continue
            chunk_order += 1
            chunks.append({
                'node_id': current_section_id or current_chapter_id,
                'type': 'text',
                'content': row['text'],
                'page': row['page'],
                'order_index': chunk_order
            })

    return pd.DataFrame(nodes), pd.DataFrame(chunks)

def main():
    df = extract_words("Designing Data Intensive Applications by Martin Kleppmann.pdf", 24, 29)
    lines = build_lines(df)
    result = classify_lines(lines)

    nodes_df, chunks_df = build_nodes_and_chunks(result)
    print(nodes_df.to_string())
    print(chunks_df.to_string())

    print(result.to_string())

main()