import socket
import threading
import json
import tkinter as tk
from tkinter import messagebox, ttk

# 伺服器地址
SERVER_HOST = '127.0.0.1'
SERVER_PORT = 5555

# 花色符號
SUIT_SYMBOLS = {
    "Hearts": "♥",
    "Diamonds": "♦",
    "Clubs": "♣",
    "Spades": "♠",
    "Joker": "🃏"
}

class ClientGUI:
    def __init__(self, master):
        self.master = master
        self.master.title("抽鬼牌遊戲")
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.receive_thread = None
        self.name = ""
        self.hand = []  # 玩家手牌
        self.selected_cards = []  # 選中的牌
        self.has_drawn = False  # 每回合是否已抽牌

        self.create_login_frame()

    def create_login_frame(self):
        """建立登入框架"""
        self.login_frame = tk.Frame(self.master)
        self.login_frame.pack(padx=10, pady=10)

        tk.Label(self.login_frame, text="請輸入你的名字:").pack(side=tk.LEFT)
        self.name_entry = tk.Entry(self.login_frame)
        self.name_entry.pack(side=tk.LEFT)
        tk.Button(self.login_frame, text="連線", command=self.connect_to_server).pack(side=tk.LEFT)

    def connect_to_server(self):
        """連接到伺服器"""
        self.name = self.name_entry.get().strip()
        if not self.name:
            messagebox.showerror("錯誤", "名字不能為空。")
            return
        try:
            self.sock.connect((SERVER_HOST, SERVER_PORT))
        except Exception as e:
            messagebox.showerror("連線錯誤", f"無法連接到伺服器: {e}")
            return

        # 發送名字給伺服器
        try:
            self.sock.sendall((self.name + "\n").encode())
        except Exception as e:
            messagebox.showerror("發送錯誤", f"無法發送名字: {e}")
            return

        # 切換到遊戲介面
        self.login_frame.destroy()
        self.create_game_frame()

        # 啟動接收訊息的執行緒
        self.receive_thread = threading.Thread(target=self.receive_messages, daemon=True)
        self.receive_thread.start()

    def create_game_frame(self):
        """建立遊戲框架"""
        self.game_frame = tk.Frame(self.master)
        self.game_frame.pack(padx=10, pady=10, fill=tk.BOTH, expand=True)

        # 遊戲資訊顯示（使用 Text 和 Scrollbar）
        info_frame = tk.Frame(self.game_frame)
        info_frame.pack(pady=5, fill=tk.X)

        self.info_scrollbar = ttk.Scrollbar(info_frame, orient=tk.VERTICAL)
        self.info_text = tk.Text(info_frame, height=3, width=60, state=tk.DISABLED, yscrollcommand=self.info_scrollbar.set, wrap=tk.WORD)
        self.info_scrollbar.config(command=self.info_text.yview)
        self.info_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.info_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # 手牌顯示（使用 Frame 和動態 Grid 佈局）
        hand_frame_container = tk.Frame(self.game_frame)
        hand_frame_container.pack(pady=5, fill=tk.BOTH, expand=True)

        self.hand_frame = tk.Frame(hand_frame_container)
        self.hand_frame.pack(fill=tk.BOTH, expand=True)

        # 綁定窗口大小調整事件，以動態調整手牌佈局
        self.master.bind("<Configure>", self.on_window_resize)

        # 操作按鈕
        self.action_frame = tk.Frame(self.game_frame)
        self.action_frame.pack(pady=5)

        self.start_button = tk.Button(self.action_frame, text="準備開始", command=self.start_game)
        self.start_button.pack(side=tk.LEFT, padx=5)

        self.draw_button = tk.Button(self.action_frame, text="抽牌", command=self.draw_card, state=tk.DISABLED)
        self.draw_button.pack(side=tk.LEFT, padx=5)

        self.discard_button = tk.Button(self.action_frame, text="配對丟棄", command=self.discard_pairs, state=tk.DISABLED)
        self.discard_button.pack(side=tk.LEFT, padx=5)

        self.end_button = tk.Button(self.action_frame, text="結束回合", command=self.end_turn, state=tk.DISABLED)
        self.end_button.pack(side=tk.LEFT, padx=5)

    def on_window_resize(self, event):
        """當窗口大小改變時，重新排列手牌按鈕"""
        self.arrange_hand()

    def arrange_hand(self):
        """根據手牌數量和窗口大小，動態排列手牌按鈕"""
        for widget in self.hand_frame.winfo_children():
            widget.grid_forget()

        if not self.hand:
            return

        # 獲取手牌區域的寬度
        self.hand_frame.update_idletasks()
        frame_width = self.hand_frame.winfo_width()
        if frame_width <= 0:
            # 初始時可能為0，忽略
            return

        # 假設每張牌按鈕的寬度為100像素（根據實際情況調整）
        card_width = 100
        padding = 10
        columns = max(1, frame_width // (card_width + padding))

        for idx, btn in enumerate(self.card_buttons):
            row = idx // columns
            col = idx % columns
            btn.grid(row=row, column=col, padx=5, pady=5, sticky='nsew')

        # 設置列的權重，以便均勻分布
        for col in range(columns):
            self.hand_frame.grid_columnconfigure(col, weight=1)

    def update_info(self, message):
        """更新遊戲資訊，限制為三行並自動捲動"""
        self.info_text.config(state=tk.NORMAL)
        self.info_text.insert(tk.END, message + "\n")
        # 限制訊息框只保留最後三行
        lines = self.info_text.get("1.0", tk.END).strip().split("\n")
        if len(lines) > 3:
            self.info_text.delete("1.0", f"{len(lines) - 2}.0")
        self.info_text.see(tk.END)
        self.info_text.config(state=tk.DISABLED)

    def update_hand_display(self):
        """更新手牌顯示"""
        for widget in self.hand_frame.winfo_children():
            widget.destroy()

        self.card_buttons = []
        for idx, card in enumerate(self.hand):
            suit = SUIT_SYMBOLS.get(card['suit'], card['suit'])
            rank = card['rank']
            if rank == 0 and card['suit'] == 'Joker':
                rank_text = '鬼牌'
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
            card_text = f"{suit} {rank_text}"

            btn = tk.Button(self.hand_frame, text=card_text, padx=10, pady=5, relief=tk.RIDGE, font=("Arial", 12),
                            command=lambda idx=idx: self.select_card(idx))
            self.card_buttons.append(btn)

        self.arrange_hand()

    def select_card(self, idx):
        """選擇手牌中的牌進行配對丟棄"""
        if idx in self.selected_cards:
            self.selected_cards.remove(idx)
            self.card_buttons[idx].config(bg="SystemButtonFace")
        else:
            if len(self.selected_cards) < 20:  # 設定一個合理的上限，例如10對
                self.selected_cards.append(idx)
                self.card_buttons[idx].config(bg="yellow")
            else:
                self.update_info("已達到選擇上限。")

        # 檢查選中的牌是否全部能夠配對
        if len(self.selected_cards) % 2 == 0 and len(self.selected_cards) > 0:
            if self.validate_selected_pairs():
                self.discard_button.config(state=tk.NORMAL)
                # self.update_info("選擇的牌可以配對丟棄。")
            else:
                self.discard_button.config(state=tk.DISABLED)
                # self.update_info("選擇的牌無法完全配對。")
        else:
            self.discard_button.config(state=tk.DISABLED)

    def validate_selected_pairs(self):
        """驗證選中的牌是否可以完全配對"""
        selected_ranks = []
        for idx in self.selected_cards:
            card = self.hand[idx]
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

    def card_to_string(self, card):
        """將卡片轉換為易讀的字串表示"""
        suit = SUIT_SYMBOLS.get(card['suit'], card['suit'])
        rank = card['rank']
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

    def start_game(self):
        """發送準備開始遊戲指令"""
        try:
            self.sock.sendall("start\n".encode())
            self.update_info("你已準備開始遊戲，等待其他玩家。")
            self.start_button.config(state=tk.DISABLED)  # 禁用開始遊戲按鈕
        except Exception as e:
            messagebox.showerror("發送錯誤", f"無法發送準備開始指令: {e}")

    def draw_card(self):
        """發送抽牌指令"""
        try:
            self.sock.sendall("draw\n".encode())
            # self.update_info("你已發送抽牌請求。")
            self.draw_button.config(state=tk.DISABLED)
            self.end_button.config(state=tk.NORMAL)  # 允許結束回合
            self.has_drawn = True  # 標記已抽牌
        except Exception as e:
            messagebox.showerror("發送錯誤", f"無法發送抽牌指令: {e}")

    def discard_pairs(self):
        """發送配對丟棄指令"""
        try:
            if len(self.selected_cards) < 2 or len(self.selected_cards) % 2 != 0:
                self.update_info("請選擇兩張或多張可配對丟棄的牌。")
                return
            # 檢查所有選擇的牌是否可以完全配對
            if not self.validate_selected_pairs():
                self.update_info("選擇的牌無法完全配對丟棄。")
                return
            # 準備丟棄的牌資訊
            discard_info = {
                'cards': [self.hand[idx] for idx in self.selected_cards]
            }
            discard_json = json.dumps(discard_info, ensure_ascii=False)
            self.sock.sendall((f"discard {discard_json}\n").encode())
            discarded_str = ', '.join([self.card_to_string(card) for card in discard_info['cards']])
            # self.update_info(f"你已發送配對丟棄請求: {discarded_str}")
            self.discard_button.config(state=tk.DISABLED)
            self.selected_cards = []
            self.update_hand_display()
        except Exception as e:
            messagebox.showerror("發送錯誤", f"無法發送配對丟棄指令: {e}")

    def end_turn(self):
        """發送結束回合指令"""
        if not self.has_drawn:
            self.update_info("你必須先抽牌才能結束回合。")
            return
        try:
            self.sock.sendall("end\n".encode())
            self.update_info("你已結束回合。")
            self.draw_button.config(state=tk.DISABLED)
            self.discard_button.config(state=tk.DISABLED)
            self.end_button.config(state=tk.DISABLED)
            self.has_drawn = False
        except Exception as e:
            messagebox.showerror("發送錯誤", f"無法發送結束回合指令: {e}")

    def find_pairs(self):
        """查找手牌中的配對（不包括鬼牌），僅返回是否有可丟棄的配對"""
        rank_counts = {}
        for card in self.hand:
            rank = card['rank']
            if rank == 0:
                continue  # 不計算鬼牌
            if rank in rank_counts:
                rank_counts[rank] += 1
            else:
                rank_counts[rank] = 1

        for count in rank_counts.values():
            if count >= 2:
                return True
        return False

    def receive_messages(self):
        """接收伺服器訊息"""
        buffer = ""
        while True:
            try:
                data = self.sock.recv(4096).decode()
                if not data:
                    self.update_info("連線已關閉。")
                    break
                buffer += data
                while '\n' in buffer:
                    line, buffer = buffer.split('\n', 1)
                    self.process_message(line)
            except Exception as e:
                self.update_info(f"接收訊息時發生錯誤: {e}")
                break

    def process_message(self, message):
        """處理伺服器訊息"""
        if message.startswith("你的手牌"):
            # 期待下一行是 JSON 手牌
            pass
        elif message.startswith("[{"):  # JSON 手牌陣列
            try:
                self.hand = json.loads(message)
                self.update_hand_display()
                # self.update_info("手牌已更新。")
            except Exception as e:
                self.update_info(f"處理手牌時發生錯誤: {e}")
        else:
            self.update_info(message)
            if "輪到你操作" in message:
                # 啟用操作按鈕
                self.draw_button.config(state=tk.NORMAL)
                self.end_button.config(state=tk.DISABLED)  # 必須先抽牌
                # 檢查是否有可配對的牌才能啟用丟棄按鈕
                if self.find_pairs():
                    self.discard_button.config(state=tk.DISABLED)  # 需手動選擇
                else:
                    self.discard_button.config(state=tk.DISABLED)
                self.has_drawn = False
            elif "現在不是你的回合" in message or "回合結束" in message:
                # 禁用操作按鈕
                self.draw_button.config(state=tk.DISABLED)
                self.discard_button.config(state=tk.DISABLED)
                self.end_button.config(state=tk.DISABLED)
            elif "贏得了遊戲" in message:
                # 這裡不再提示，僅等待伺服器的再來一局請求
                pass
            elif "遊戲結束，是否再來一局？" in message:
                self.prompt_play_again_request()
            elif "有人拒絕再來一局，遊戲結束。" in message:
                messagebox.showinfo("遊戲結束", message)
                self.sock.close()
                self.master.quit()
            elif "所有玩家同意再來一局，請準備開始。" in message:
                messagebox.showinfo("遊戲重新開始", message)
                self.clear_hand_display()
                self.start_button.config(state=tk.NORMAL)  # 啟用開始遊戲按鈕
            elif "你丟棄的牌是" in message or "你抽到的牌是" in message:
                # 伺服器已發送更新後的手牌，等待接收
                pass

    def prompt_play_again_request(self):
        """當伺服器請求是否再來一局時，提示使用者"""
        response = messagebox.askyesno("再來一局", "遊戲結束，是否再來一局？")
        if response:
            try:
                self.sock.sendall("playagain yes\n".encode())
            except Exception as e:
                messagebox.showerror("發送錯誤", f"無法發送再來一局指令: {e}")
        else:
            try:
                self.sock.sendall("playagain no\n".encode())
            except Exception as e:
                messagebox.showerror("發送錯誤", f"無法發送不再來一局指令: {e}")

    def clear_hand_display(self):
        """清空手牌顯示"""
        self.hand = []
        self.selected_cards = []
        self.update_hand_display()

    def close_connection(self):
        """關閉連線並退出"""
        try:
            self.sock.close()
        except:
            pass
        self.master.quit()

def main():
    root = tk.Tk()
    client_gui = ClientGUI(root)
    root.protocol("WM_DELETE_WINDOW", client_gui.close_connection)
    root.mainloop()

if __name__ == "__main__":
    main()
