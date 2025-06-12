import os
import re
import itertools
import random
from treys import Card, Evaluator

def convert_str_cards_to_treys(cards_str_list):
    treys_cards = []
    for c in cards_str_list:
        rank = c[0].upper()
        suit = c[1].lower()
        card_str = rank + suit
        treys_cards.append(Card.new(card_str))
    return treys_cards

def get_partial_board(hand):
    """
    Hero가 쇼다운한 시점까지 공개된 보드를 반환.
    리버까지 깔린 경우는 None을 반환하여 제외.
    """
    shows_index = hand.find('Hero: shows')
    river_index = hand.find('*** RIVER ***')
    if river_index != -1 and river_index < shows_index:
        return None  # 리버 이후 쇼다운: 제외

    flop = turn = river = []
    flop_match = re.search(r'\*\*\* FLOP \*\*\* \[([^\]]+)\]', hand)
    if flop_match:
        flop = flop_match.group(1).split()

    turn_match = re.search(r'\*\*\* TURN \*\*\* \[[^\]]+\] \[([^\]]+)\]', hand)
    if turn_match:
        turn = turn_match.group(1).split()

    # 여기서 RIVER는 포함하지 않음
    board = []
    if flop_match and flop_match.start() < shows_index:
        board += flop
    if turn_match and turn_match.start() < shows_index:
        board += turn

    return board

def calc_equity_exhaustive(hero_cards, opp_cards, board_cards_str, max_samples=10000):
    evaluator = Evaluator()

    used_cards = set(hero_cards + opp_cards + convert_str_cards_to_treys(board_cards_str))
    all_cards = [Card.new(r + s) for r in '23456789TJQKA' for s in 'shdc']
    remaining_cards = [c for c in all_cards if c not in used_cards]

    num_missing = 5 - len(board_cards_str)
    if num_missing == 0:
        board = convert_str_cards_to_treys(board_cards_str)
        return calc_equity(hero_cards, opp_cards, board)

    all_combos = list(itertools.combinations(remaining_cards, num_missing))
    total = len(all_combos)

    if total > max_samples:
        all_combos = random.sample(all_combos, max_samples)

    wins = ties = 0
    for combo in all_combos:
        full_board = convert_str_cards_to_treys(board_cards_str) + list(combo)
        hero_score = evaluator.evaluate(full_board, hero_cards)
        opp_score = evaluator.evaluate(full_board, opp_cards)
        if hero_score < opp_score:
            wins += 1
        elif hero_score == opp_score:
            ties += 1

    return [wins / len(all_combos), ties / len(all_combos)]

def calc_equity(hero_cards, opp_cards, board_cards):
    evaluator = Evaluator()
    hero_score = evaluator.evaluate(board_cards, hero_cards)
    opp_score = evaluator.evaluate(board_cards, opp_cards)
    if hero_score < opp_score:
        return 1.0
    elif hero_score > opp_score:
        return 0.0
    else:
        return 0.5

def extract_hero_final_stacks(hands):
    final_stacks = [0] * (len(hands) + 1)
    for i in range(len(hands)):
        m_stack = re.search(r'Seat \d+: Hero \(([",\d]+) in chips\)', hands[i])
        if m_stack:
            final_stacks[i + 1] = int(m_stack.group(1).replace(',', ''))
    return final_stacks

def Adjs(buy_in, stack):
    return buy_in * pow(abs(stack), 0.9)

def filter_hands_and_compute_equity(hands_text):
    hands = hands_text.strip().split('\n\n')
    final_stacks_list = extract_hero_final_stacks(hands)
    MTT_start_stacks = final_stacks_list[-1]
    results = []

    for hand in hands:
        
        if 'Hero: shows' not in hand:
            continue

        # 상대가 정확히 한 명만 showdown한 경우만 처리
        if len(re.findall(r'Showed \[', hand, re.IGNORECASE)) != 2:
            continue

        board_cards_str = get_partial_board(hand)
        if board_cards_str is None:
            continue  # 리버까지 깔린 경우 제외

        m_stack = re.search(r'Seat \d+: Hero \(([\d,]+) in chips\)', hand)
        start_stack = int(m_stack.group(1).replace(',', '')) if m_stack else None
        start_stack /= MTT_start_stacks

        idx = hands.index(hand)
        final_stack = final_stacks_list[idx] / MTT_start_stacks

        m_collected = re.search(r'Hero collected ([\d,]+) from pot', hand)
        collected = int(m_collected.group(1).replace(',', '')) if m_collected else 0
        collected /= MTT_start_stacks

        m_total_pot = re.search(r'Total pot ([\d,]+)', hand)
        total_pot = int(m_total_pot.group(1).replace(',', '')) if m_total_pot else None
        total_pot /= MTT_start_stacks

        m_hero_cards = re.search(r'Dealt to Hero \[([^\]]+)\]', hand)
        hero_cards_str = m_hero_cards.group(1).split() if m_hero_cards else []

        m_buy_in = re.search(r'\$([\d]+(?:\.\d+)?)\b', hand)
        buy_in = float(m_buy_in.group(1)) if m_buy_in else None
        if buy_in is None:
            m_buy_in = re.search(r'\¥([\d]+(?:\.\d+)?)\b', hand)
            buy_in = float(m_buy_in.group(1)) * 0.14

        opp_cards_str = []
        for m in re.finditer(r'Seat \d+: (?!Hero)(?:.+?) showed \[([^\]]+)\]', hand):
            opp_cards_str += m.group(1).split()

        try:
            hero_cards_treys = convert_str_cards_to_treys(hero_cards_str)
            opp_cards_treys = convert_str_cards_to_treys(opp_cards_str)

            if len(hero_cards_treys) != 2 or len(opp_cards_treys) != 2 or len(board_cards_str) > 5:
                continue

            equity = calc_equity_exhaustive(hero_cards_treys, opp_cards_treys, board_cards_str)

        except Exception as e:
            print("Card conversion or evaluation error:", e)
            continue
        
        win_value = Adjs(buy_in, final_stack - collected + total_pot)
        tie_value = Adjs(buy_in, final_stack - collected + total_pot / 2)
        lose_value = Adjs(buy_in, final_stack - collected)
        allinEV = win_value * equity[0] + tie_value * equity[1] + lose_value * (1 - equity[0] - equity[1])
        realvalue = Adjs(buy_in, final_stack)
        luck = realvalue - allinEV

        results.append({
            'start_stack': start_stack,
            'final_stack': final_stack,
            'collected': collected,
            'total_pot': total_pot,
            'equity': equity[0] + equity[1] / 2,
            'buy_in': buy_in,
            'luck': luck
        })

    return results

def process_poker_hands_from_file(file_path):
    with open(file_path, 'r', encoding='utf-8') as f:
        hands_text = f.read()

    results = filter_hands_and_compute_equity(hands_text)
    totalluck = sum(r['luck'] for r in results)
    buy_in = results[0]['buy_in'] if results else 0.0

    """
    for i, r in enumerate(results):
        if i!=0:
            print("")
        print(f"--- Hand {i+1} ---")
        print(f"Start Stack: {r['start_stack']}")
        print(f"Final Stack: {r['final_stack']}")
        print(f"Collected: {r['collected']}")
        print(f"Total Pot: {r['total_pot']}")
        print(f"Equity: {r['equity']:.4f}")
        print(f"Buy-in: {r['buy_in']:.2f}")
        print(f"Luck: {r['luck']:.2f}")
    """

    return [totalluck, buy_in]

def process_all_txt_in_folder(folder_path):
    results = [0.0, 0.0]
    for filename in os.listdir(folder_path):
        if filename.endswith(".txt"):
            full_path = os.path.join(folder_path, filename)
            result = process_poker_hands_from_file(full_path)
            results[0] += result[0]
            results[1] += result[1]
            if result[1] != 0.0:
                print(f"Processed {filename}: Luck = {result[0]:.2f}$, Buy-in = {result[1]:.2f}$")
            else:
                print(f"Skipping {filename} due to no valid hands.")
    print(f"Total Luck: {results[0]:.2f}$, Total Buy-in: {results[1]:.2f}$")


def main(folder_path):
    process_all_txt_in_folder(folder_path)

if __name__ == "__main__":
    folder_path = "C:/Users/bonma/OneDrive/바탕 화면/HandHistories"
    main(folder_path)
