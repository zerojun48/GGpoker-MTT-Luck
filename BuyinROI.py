import os
import re
import pandas as pd
import matplotlib.pyplot as plt
import numpy as np
from pathlib import Path

def _parse_buy_in(content: str):
    """
    Buy-in 라인에서 본전+레이크 형태를 안전하게 합산.
    예: 'Buy-in: $4.6+$0.4' -> 5.0, 'Buy-in: $46+$4' -> 50.0
    """
    m = re.search(r'Buy-in:\s*\$?([\d.,]+)(?:\s*\+\s*\$?([\d.,]+))?', content, flags=re.IGNORECASE)
    if m:
        major = float(m.group(1).replace(',', ''))
        rake = float(m.group(2).replace(',', '')) if m.group(2) else 0.0
        return round(major + rake, 2)
    # 예외: Weekender Day1인데 Buy-in 라인이 누락된 특수 케이스는 50으로 처리
    if re.search(r'The Weekender\s*\[Day\s*1', content, flags=re.IGNORECASE) and 'Buy-in:' not in content:
        return 50.0
    return 0.0

def _is_day1_advanced(content: str):
    return bool(re.search(r'You have advanced to Day\s*2', content, flags=re.IGNORECASE))

def _reentry_count(content: str):
    # 'You made 1 re-entries' → 1
    m = re.search(r'You made\s+(\d+)\s+re-entries', content, flags=re.IGNORECASE)
    return int(m.group(1)) if m else 0

def _received_amount(content: str):
    """
    상금 파싱:
    - 'You received a total of $XX' → float
    - 'received a total of 0 chips' → 0.0
    - 'You finished ... $XX' (일부 파일이 이 형태) → float
    """
    m = re.search(r'You received a total of \$([\d,]+(?:\.\d+)?)', content, flags=re.IGNORECASE)
    if m:
        return float(m.group(1).replace(',', ''))

    # 0 chips 처리
    if re.search(r'(received a total of|You received a total of)\s+0\s+chips', content, flags=re.IGNORECASE):
        return 0.0

    # 백업: 결과 라인에 달러만 있는 경우
    m2 = re.search(r'\bHero,\s*\$([\d,]+(?:\.\d+)?)', content, flags=re.IGNORECASE)
    if m2:
        return float(m2.group(1).replace(',', ''))

    return None  # 못 찾음

def parse_tournament_file(file_path: Path):
    """
    단일 파일을 파싱해서 dict들의 리스트를 반환 (re-entry로 여러 엔트리가 생길 수 있음)
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # Buy-in 계산 (수수료 포함 합산)
        buy_in = _parse_buy_in(content)
        if buy_in <= 0:
            # 예외: Weekender Day1 누락 케이스는 _parse_buy_in에서 50 처리함
            return []

        # Day1에서 Day2 진출이면 Day1 기록은 추가하지 않음
        if _is_day1_advanced(content):
            return []

        # 상금/칩 파싱
        received = _received_amount(content)

        # re-entry 수 추출
        rcount = _reentry_count(content)

        # Day1 여부
        is_day1 = bool(re.search(r'\[Day\s*1[^\]]*\]', content, flags=re.IGNORECASE))

        records = []

        if is_day1:
            # Day1: 칩 0(또는 $0)으로 끝났으면 (1+re-entries)개 (buy_in, 0) 추가
            chips_zero = bool(re.search(r'0\s+chips', content, flags=re.IGNORECASE))
            if chips_zero or (received is not None and received == 0.0) or received is None:
                entries = 1 + rcount
                for i in range(entries):
                    records.append({
                        'file_name': f"{file_path.name}#{i+1}/{entries}" if entries > 1 else file_path.name,
                        'buy_in': buy_in,
                        'received': 0.0,
                        'profit': -buy_in,
                        'roi': -100.0
                    })
                return records
            # (희귀) Day1인데 달러 상금이 있으면 단일 엔트리
            if received is not None:
                records.append({
                    'file_name': file_path.name,
                    'buy_in': buy_in,
                    'received': received,
                    'profit': received - buy_in,
                    'roi': ((received - buy_in) / buy_in) * 100 if buy_in > 0 else 0.0
                })
                return records

        # ✅ 일반 토너먼트(또는 Final/Day2+) 리엔트리 반영
        # - 상금이 0(또는 0 chips)이면 Day1과 동일하게 (1+re-entries)개 (buy_in, 0) 추가
        # - 상금이 >0 이면 단일 엔트리
        chips_zero_any = bool(re.search(r'0\s+chips', content, flags=re.IGNORECASE))
        if (received is not None and received == 0.0) or chips_zero_any:
            entries = 1 + rcount if rcount >= 0 else 1
            for i in range(entries):
                records.append({
                    'file_name': f"{file_path.name}#{i+1}/{entries}" if entries > 1 else file_path.name,
                    'buy_in': buy_in,
                    'received': 0.0,
                    'profit': -buy_in,
                    'roi': -100.0
                })
            return records

        # 상금이 있는 일반/최종일 이벤트
        if received is not None:
            records.append({
                'file_name': file_path.name,
                'buy_in': buy_in,
                'received': received,
                'profit': received - buy_in,
                'roi': ((received - buy_in) / buy_in) * 100 if buy_in > 0 else 0.0
            })
            return records

        return []

    except Exception as e:
        print(f"파일 {file_path} 파싱 중 오류: {e}")
        return []


def analyze_folder(folder_path):
    """폴더 내 모든 txt 파일을 분석"""
    folder = Path(folder_path)

    if not folder.exists():
        raise ValueError(f"폴더를 찾을 수 없습니다: {folder_path}")

    data = []
    txt_files = list(folder.glob("*.txt"))

    if not txt_files:
        raise ValueError(f"폴더에 txt 파일이 없습니다: {folder_path}")

    print(f"{len(txt_files)}개의 txt 파일을 발견했습니다.")

    for file_path in txt_files:
        results = parse_tournament_file(file_path)
        if results:
            data.extend(results)

    if not data:
        raise ValueError("유효한 토너먼트 데이터를 찾을 수 없습니다.")

    print(f"{len(data)}개의 유효한 토너먼트 엔트리를 추출했습니다.")
    return pd.DataFrame(data)

def categorize_buy_in(buy_in):
    """Buy-in 값을 구간별로 분류"""
    if buy_in <= 1:
        return '[0, 1]'
    elif buy_in <= 2:
        return '(1, 2]'
    elif buy_in <= 5:
        return '(2, 5]'
    elif buy_in <= 10:
        return '(5, 10]'
    elif buy_in <= 25:
        return '(10, 25]'
    else:
        return '(25, ∞)'

def analyze_by_ranges(df):
    """Buy-in 구간별 수익률 분석"""
    df = df.copy()
    df['range'] = df['buy_in'].apply(categorize_buy_in)

    range_analysis = df.groupby('range', sort=False).agg({
        'buy_in': ['count', 'sum', 'mean'],
        'received': ['sum', 'mean'],
        'profit': 'sum'
    }).round(2)

    range_analysis.columns = ['count', 'total_buy_in', 'avg_buy_in', 'total_received', 'avg_received', 'total_profit']
    range_analysis['roi'] = (range_analysis['total_profit'] / range_analysis['total_buy_in'] * 100).round(2)

    range_order = ['[0, 1]', '(1, 2]', '(2, 5]', '(5, 10]', '(10, 25]', '(25, ∞)']
    range_analysis = range_analysis.reindex([r for r in range_order if r in range_analysis.index])

    return range_analysis

def create_scatter_plot(df):
    """Buy-in vs Received 산점도 생성"""
    plt.figure(figsize=(12, 8))
    colors = ['red' if roi < 0 else 'green' if roi > 0 else 'gray' for roi in df['roi']]
    plt.scatter(df['buy_in'], df['received'], c=colors, alpha=0.6, s=50)

    max_val = max(df['buy_in'].max(), df['received'].max())
    plt.xlim(0, max_val)
    plt.ylim(0, max_val)
    plt.plot([0, max_val], [0, max_val], 'k--', alpha=0.5, linewidth=1, label='손익분기선 (y=x)')

    plt.xlabel('Buy-in ($)', fontsize=12)
    plt.ylabel('Received ($)', fontsize=12)
    plt.title('Buy-in vs Received 산점도', fontsize=14, fontweight='bold')
    plt.grid(True, alpha=0.3)

    from matplotlib.patches import Patch
    legend_elements = [
        Patch(facecolor='green', alpha=0.6, label='수익 (ROI > 0%)'),
        Patch(facecolor='red', alpha=0.6, label='손실 (ROI < 0%)'),
        Patch(facecolor='gray', alpha=0.6, label='손익분기 (ROI = 0%)')
    ]
    plt.legend(handles=legend_elements, loc='upper left')
    plt.tight_layout()
    return plt

def create_roi_bar_chart(range_analysis):
    """구간별 ROI 막대 그래프 생성"""
    plt.figure(figsize=(12, 6))
    ranges = range_analysis.index
    roi_values = range_analysis['roi']
    colors = ['green' if roi >= 0 else 'red' for roi in roi_values]
    bars = plt.bar(ranges, roi_values, color=colors, alpha=0.7)

    for bar, roi in zip(bars, roi_values):
        height = bar.get_height()
        plt.text(bar.get_x() + bar.get_width()/2., height + (1 if height >= 0 else -3),
                 f'{roi}%', ha='center', va='bottom' if height >= 0 else 'top', fontweight='bold')

    plt.xlabel('Buy-in 구간 ($)', fontsize=12)
    plt.ylabel('ROI (%)', fontsize=12)
    plt.title('Buy-in 구간별 ROI', fontsize=14, fontweight='bold')
    plt.grid(True, alpha=0.3, axis='y')
    plt.axhline(y=0, color='black', linestyle='-', linewidth=0.5)
    plt.tight_layout()
    return plt

def print_summary(df, range_analysis):
    """분석 결과 요약 출력"""
    print("\n" + "="*60)
    print("포커 토너먼트 분석 결과")
    print("="*60)

    total_tournaments = len(df)
    total_buy_in = df['buy_in'].sum()
    total_received = df['received'].sum()
    total_profit = df['profit'].sum()
    overall_roi = (total_profit / total_buy_in * 100) if total_buy_in > 0 else 0

    print(f"\n📊 전체 통계:")
    print(f"  • 총 엔트리 수: {total_tournaments}개")
    print(f"  • 총 Buy-in: ${total_buy_in:.2f}")
    print(f"  • 총 상금: ${total_received:.2f}")
    print(f"  • 총 손익: ${total_profit:.2f}")
    print(f"  • 전체 ROI: {overall_roi:.2f}%")

    print(f"\n📈 Buy-in 구간별 분석:")
    print(f"{'구간':^12} {'엔트리수':^8} {'총 Buy-in':^10} {'총 상금':^10} {'총 손익':^10} {'ROI (%)':^8}")
    print("-" * 75)

    for range_name, row in range_analysis.iterrows():
        roi_symbol = "📈" if row['roi'] >= 0 else "📉"
        print(f"{range_name:^12} {int(row['count']):^8} ${row['total_buy_in']:^9.2f} ${row['total_received']:^9.2f} "
              f"${row['total_profit']:^9.2f} {row['roi']:^7.2f}% {roi_symbol}")

    best_range = range_analysis.loc[range_analysis['roi'].idxmax()]
    worst_range = range_analysis.loc[range_analysis['roi'].idxmin()]

    print(f"\n🏆 가장 높은 ROI 구간: {range_analysis['roi'].idxmax()} ({best_range['roi']:.2f}%)")
    print(f"⚠️  가장 낮은 ROI 구간: {range_analysis['roi'].idxmin()} ({worst_range['roi']:.2f}%)")

def main():
    """메인 함수"""
    folder_path = "C:/Users/bonma/OneDrive/바탕 화면/GameResults"

    try:
        print("파일들을 분석하는 중...")
        df = analyze_folder(folder_path)
        range_analysis = analyze_by_ranges(df)

        print_summary(df, range_analysis)

        print("\n그래프를 생성하는 중...")
        scatter_fig = create_scatter_plot(df)
        scatter_fig.show()

        roi_fig = create_roi_bar_chart(range_analysis)
        roi_fig.show()

        save_option = input("\n분석 결과를 CSV 파일로 저장하시겠습니까? (y/n): ").strip().lower()
        if save_option == 'y':
            df.to_csv('tournament_details.csv', index=False, encoding='utf-8-sig')
            print("상세 데이터가 'tournament_details.csv'에 저장되었습니다.")

            range_analysis.to_csv('range_analysis.csv', encoding='utf-8-sig')
            print("구간별 분석 결과가 'range_analysis.csv'에 저장되었습니다.")

        input("\n아무 키나 누르면 종료합니다...")

    except Exception as e:
        print(f"오류 발생: {e}")
        input("아무 키나 누르면 종료합니다...")

if __name__ == "__main__":
    main()
