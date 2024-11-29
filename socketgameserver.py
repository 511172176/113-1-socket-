import socket
import threading
import random
import json

# 遊戲參數
HOST = '0.0.0.0'
PORT = 5555
MIN_PLAYERS = 2  # 最小玩家數量
MAX_PLAYERS = 4  # 最大玩家數量

# 撲克牌生成，包括兩張鬼牌
suits = ['Hearts', 'Diamonds', 'Clubs', 'Spades']
ranks = list(range(1, 14))  # 1: Ace, 11: Jack, 12: Queen, 13: King
joker = {'suit': 'Joker', 'rank': 0}  # 將鬼牌的 rank 設置為 0

def create_deck():
    """建立一副包含鬼牌的撲克牌"""
    deck = [{'suit': suit, 'rank': rank} for suit in suits for rank in ranks]
    deck.extend([joker.copy(), joker.copy()])  # 加入兩張鬼牌
    return deck

class Player:
    def __init__(self, conn, addr, name):
        self.conn = conn
        self.addr = addr
        self.name = name
        self.hand = []
        self.ready = False  # 表示玩家是否準備好
        self.has_drawn = False  # 每回合是否已抽牌
        self.play_again = None  # 玩家是否想再玩一局

class GameServer:
    def __init__(self, host, port):
        self.players = []
        self.host = host
        self.port = port
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.deck = []
        self.current_player = 0
        self.game_started = False
        self.lock = threading.Lock()  # 用於線程安全的鎖
        self.waiting_for_play_again = False

    def start_server(self):
        """啟動伺服器"""
        self.server_socket.bind((self.host, self.port))
        self.server_socket.listen()
        print(f"伺服器啟動，監聽 {self.host}:{self.port}")

        accept_thread = threading.Thread(target=self.accept_connections, daemon=True)
        accept_thread.start()

        try:
            while True:
                pass
        except KeyboardInterrupt:
            print("伺服器正在關閉...")
            self.server_socket.close()

    def accept_connections(self):
        """接受玩家連線"""
        while True:
            try:
                conn, addr = self.server_socket.accept()
                print(f"玩家連線: {addr}")
                conn.sendall("請輸入你的名字:\n".encode())
                name = conn.recv(1024).decode().strip()
                if not name:
                    conn.sendall("名字不能為空，斷開連線。\n".encode())
                    conn.close()
                    continue
                with self.lock:
                    if len(self.players) >= MAX_PLAYERS:
                        conn.sendall("遊戲已滿員，無法加入。\n".encode())
                        conn.close()
                        continue
                player = Player(conn, addr, name)
                with self.lock:
                    self.players.append(player)
                print(f"玩家 {name} 已加入遊戲。")
                conn.sendall(f"歡迎 {name} 加入遊戲！\n".encode())

                # 啟動一個執行緒處理玩家訊息
                threading.Thread(target=self.handle_player, args=(player,), daemon=True).start()
            except Exception as e:
                print(f"接受連線時出錯: {e}")
                break

    def handle_player(self, player):
        """處理單個玩家的訊息"""
        try:
            while True:
                data = player.conn.recv(4096).decode().strip()
                if not data:
                    print(f"玩家 {player.name} 已斷開連線。")
                    break
                print(f"收到來自 {player.name} 的指令: {data}")

                if not self.waiting_for_play_again:
                    # Normal game commands
                    if data.lower() == "start":
                        player.ready = True
                        self.broadcast(f"{player.name} 已準備開始遊戲。")
                        if self.check_all_ready():
                            self.start_game()
                    elif self.game_started:
                        if self.players[self.current_player] == player:
                            if data.lower().startswith("draw"):
                                self.handle_draw(player)
                                # player.conn.sendall("你可以繼續操作，輸入 'discard' 配對丟棄 或 'end' 結束回合。\n".encode())
                            elif data.lower().startswith("discard"):
                                # 提取丟棄的牌資訊
                                try:
                                    _, discard_json = data.split(" ", 1)
                                    discard_info = json.loads(discard_json)
                                    cards_to_discard = discard_info.get('cards', [])
                                    if len(cards_to_discard) < 2 or len(cards_to_discard) % 2 != 0:
                                        player.conn.sendall("丟棄必須是兩張或多張偶數張牌。\n".encode())
                                        continue
                                    # 驗證每一對是否符合配對規則
                                    if not self.validate_discard_pairs(player, cards_to_discard):
                                        player.conn.sendall("丟棄的牌必須成對數字相同且非鬼牌。\n".encode())
                                        continue
                                    # 驗證玩家手中是否有這些牌
                                    if not self.validate_player_hand(player, cards_to_discard):
                                        player.conn.sendall("你手中沒有這些牌，無法丟棄。\n".encode())
                                        continue
                                    self.handle_discard(player, cards_to_discard)
                                    # player.conn.sendall("你已完成配對丟棄。\n".encode())
                                except Exception as e:
                                    player.conn.sendall("丟棄指令格式錯誤。\n".encode())
                                    continue
                            elif data.lower().startswith("end"):
                                # 確保玩家已經抽牌
                                if not player.has_drawn:
                                    player.conn.sendall("你必須先抽牌才能結束回合。\n".encode())
                                    continue
                                # 結束回合，切換到下一位玩家
                                self.current_player = (self.current_player + 1) % len(self.players)
                                self.notify_current_player()
                            elif data.lower().startswith("playagain"):
                                # Player responds to play again request
                                try:
                                    _, response = data.split(" ", 1)
                                    response = response.lower()
                                    if response == "yes":
                                        player.play_again = True
                                    elif response == "no":
                                        player.play_again = False
                                    else:
                                        player.conn.sendall("請回應 'playagain yes' 或 'playagain no'。\n".encode())
                                        continue
                                    self.check_play_again()
                                except ValueError:
                                    player.conn.sendall("請使用格式 'playagain yes' 或 'playagain no'。\n".encode())
                                    continue
                            else:
                                player.conn.sendall("無效的指令，請重新輸入。\n".encode())
                                continue

                            # 檢查遊戲結束條件
                            if len(player.hand) == 0:
                                self.broadcast(f"{player.name} 贏得了遊戲！")
                                self.game_started = False
                                self.waiting_for_play_again = True
                                self.request_play_again()
                                break
                        else:
                            player.conn.sendall("現在不是你的回合，請等待。\n".encode())
                    else:
                        player.conn.sendall("遊戲尚未開始，請等待其他玩家準備。\n".encode())
                else:
                    # Waiting for players to agree to play again
                    if data.lower().startswith("playagain"):
                        try:
                            _, response = data.split(" ", 1)
                            response = response.lower()
                            if response == "yes":
                                player.play_again = True
                            elif response == "no":
                                player.play_again = False
                            else:
                                player.conn.sendall("請回應 'playagain yes' 或 'playagain no'。\n".encode())
                                continue
                            self.check_play_again()
                        except ValueError:
                            player.conn.sendall("請使用格式 'playagain yes' 或 'playagain no'。\n".encode())
                            continue
                    else:
                        player.conn.sendall("請回答 'playagain yes' 或 'playagain no' 以決定是否再來一局。\n".encode())
        except Exception as e:
            print(f"處理玩家 {player.name} 時發生錯誤: {e}")
        finally:
            player.conn.close()
            with self.lock:
                if player in self.players:
                    self.players.remove(player)
            self.broadcast(f"玩家 {player.name} 已離開遊戲。")
            print(f"玩家 {player.name} 已離開遊戲。")

    def validate_discard_pairs(self, player, cards):
        """驗證所有被丟棄的牌是否能完全配對"""
        selected_ranks = []
        for card in cards:
            if card['suit'] == 'Joker':
                return False  # 鬼牌不能被丟棄
            selected_ranks.append(card['rank'])
        rank_counts = {}
        for rank in selected_ranks:
            if rank in rank_counts:
                rank_counts[rank] += 1
            else:
                rank_counts[rank] = 1
        for count in rank_counts.values():
            if count % 2 != 0:
                return False
        return True

    def validate_player_hand(self, player, cards):
        """驗證玩家手中是否擁有所有欲丟棄的牌"""
        temp_hand = player.hand.copy()
        for card in cards:
            if card in temp_hand:
                temp_hand.remove(card)
            else:
                return False
        return True

    def check_all_ready(self):
        """檢查是否所有玩家都已準備好且至少有最小玩家數量"""
        if len(self.players) < MIN_PLAYERS:
            return False
        return all(player.ready for player in self.players)

    def start_game(self):
        """開始遊戲並分發手牌"""
        with self.lock:
            self.game_started = True
            self.waiting_for_play_again = False
            print("所有玩家都已準備好，遊戲開始，正在分發牌組...")
            self.deck = create_deck()
            random.shuffle(self.deck)

            # 清除之前的 play_again 回應
            for player in self.players:
                player.play_again = None

            # 平均分配牌給玩家
            player_count = len(self.players)
            for i, card in enumerate(self.deck):
                self.players[i % player_count].hand.append(card)

            # 通知玩家他們的手牌
            for player in self.players:
                self.send_hand(player)
                player.conn.sendall("遊戲已開始，等待你的操作！\n".encode())
                player.has_drawn = False  # 初始化每個玩家的抽牌狀態

            self.notify_current_player()

    def notify_current_player(self):
        """通知當前玩家進行操作"""
        if not self.game_started:
            return
        if not self.players:
            return
        current_player = self.players[self.current_player]
        try:
            current_player.conn.sendall("輪到你操作，點擊抽牌或配對丟棄，或結束回合。\n".encode())
        except Exception as e:
            print(f"通知玩家 {current_player.name} 時出錯: {e}")

    def send_hand(self, player):
        """發送玩家的手牌"""
        try:
            player.conn.sendall("你的手牌:\n".encode())
            # 將手牌中的鬼牌標記為不可丟棄
            hand_display = []
            for card in player.hand:
                hand_display.append(card)
            hand_json = json.dumps(hand_display, ensure_ascii=False)
            player.conn.sendall((hand_json + "\n").encode())
        except Exception as e:
            print(f"發送手牌時出錯: {e}")

    def handle_draw(self, player):
        """處理玩家抽牌"""
        with self.lock:
            next_player_index = (self.current_player + 1) % len(self.players)
            next_player = self.players[next_player_index]

            available_cards = [card for card in next_player.hand]  # 現在允許抽到鬼牌

            if not available_cards:
                player.conn.sendall("下一位玩家沒有可抽的牌。\n".encode())
                return

            # 從下一位玩家的手牌中隨機抽一張（包括鬼牌）
            drawn_card = random.choice(available_cards)
            next_player.hand.remove(drawn_card)
            player.hand.append(drawn_card)
            self.broadcast(f"{player.name} 從 {next_player.name} 那裡抽了一張牌 {self.card_to_string(drawn_card)}。")
            self.send_hand(player)
            self.send_hand(next_player)  # 確保被抽方手牌即時更新
            player.has_drawn = True  # 標記玩家已抽牌

            # 檢查遊戲結束條件（檢查被抽牌方的手牌是否為空）
            if len(next_player.hand) == 0:
                self.broadcast(f"{next_player.name} 贏得了遊戲！")
                self.game_started = False
                self.waiting_for_play_again = True
                self.request_play_again()

    def handle_discard(self, player, cards):
        """處理玩家配對丟棄"""
        with self.lock:
            # 移除丟棄的牌
            for card in cards:
                if card in player.hand:
                    player.hand.remove(card)

            # 通知所有玩家
            discarded_str = ', '.join([self.card_to_string(card) for card in cards])
            self.broadcast(f"{player.name} 丟棄了牌: {discarded_str}")
            self.send_hand(player)

            # 檢查遊戲結束條件
            if len(player.hand) == 0:
                self.broadcast(f"{player.name} 贏得了遊戲！")
                self.game_started = False
                self.waiting_for_play_again = True
                self.request_play_again()

    def broadcast(self, message):
        """廣播訊息給所有玩家"""
        for player in self.players:
            try:
                player.conn.sendall((message + "\n").encode())
            except Exception as e:
                print(f"廣播給 {player.name} 時出錯: {e}")

    def card_to_string(self, card):
        """將卡片轉換為易讀的字串表示"""
        SUIT_SYMBOLS = {
            "Hearts": "♥",
            "Diamonds": "♦",
            "Clubs": "♣",
            "Spades": "♠",
            "Joker": "🃏"
        }
        rank = card['rank']
        suit = SUIT_SYMBOLS.get(card['suit'], card['suit'])
        if rank == 0 and card['suit'] == 'Joker':
            return '鬼牌'
        elif rank == 1:
            rank_text = 'A'
        elif rank == 11:
            rank_text = 'J'
        elif rank == 12:
            rank_text = 'Q'
        elif rank == 13:
            rank_text = 'K'
        else:
            rank_text = str(rank)
        return f"{suit} {rank_text}"

    def request_play_again(self):
        """向所有玩家請求是否再玩一局"""
        self.broadcast("遊戲結束，是否再來一局？請回應 'playagain yes' 或 'playagain no'。")

    def check_play_again(self):
        """檢查所有玩家是否都同意再玩一局"""
        with self.lock:
            if any(player.play_again is False for player in self.players):
                self.broadcast("有人拒絕再來一局，遊戲結束。")
                self.game_started = False
                self.waiting_for_play_again = False
                # 重置玩家的準備狀態
                for player in self.players:
                    player.ready = False
            elif all(player.play_again for player in self.players):
                self.broadcast("所有玩家同意再來一局，請準備開始。")
                self.reset_game()
                # 等待玩家再次點擊 "start" 按鈕
            # Else, still waiting for some players to respond

    def reset_game(self):
        """重置遊戲狀態，準備重新開始"""
        self.deck = []
        for player in self.players:
            player.hand = []
            player.ready = False  # 重置準備狀態
            player.has_drawn = False
            player.play_again = None
        self.current_player = 0
        self.game_started = False
        self.waiting_for_play_again = False

if __name__ == "__main__":
    server = GameServer(HOST, PORT)
    server.start_server()
