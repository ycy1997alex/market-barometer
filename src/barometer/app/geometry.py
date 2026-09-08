"""視窗尺寸：依螢幕解析度換算，不寫死像素。

規格：**由上到下 3%~87%、由左到右 3%~97%。**

    x      = 螢幕寬 × 3%
    右緣   = 螢幕寬 × 97%     → 寬 = 94%
    y      = 螢幕高 × 3%
    下緣   = 螢幕高 × 87%     → 高 = 84%

下緣停在 87% 而不是 97%，底下那 13% 是留給工作列的。

寫死 `1080x620` 這種尺寸在 4K 螢幕上會變成角落一個小方塊，在 1366×768 的
筆電上又會超出畫面。換算成百分比之後兩邊都合理。

**這是純函式，沒有 import tkinter** —— 螢幕尺寸由呼叫端量好傳進來。
好處是它能離線測：少算一次邊界、或把 87% 當成「高度」而不是「下緣」，
在畫面上看起來都差不多對，肉眼驗不出來，但測試驗得出來。
"""
from __future__ import annotations

from dataclasses import dataclass

LEFT_PCT = 0.03
RIGHT_PCT = 0.97
TOP_PCT = 0.03
BOTTOM_PCT = 0.87

# 小於這個尺寸，表格會擠到看不出欄位。寧可超出百分比也要保住可讀性。
MIN_WIDTH = 900
MIN_HEIGHT = 560

# 扣掉外框之後至少要剩這麼多 —— 量錯的時候不能收出一個沒有內容的視窗
MIN_FRAME_REMAINDER = 200


@dataclass(frozen=True, slots=True)
class Box:
    width: int
    height: int
    x: int
    y: int

    def as_geometry(self) -> str:
        """tkinter 的 `geometry()` 字串格式。"""
        return f"{self.width}x{self.height}+{self.x}+{self.y}"


def window_box(screen_width: int, screen_height: int) -> Box:
    """把螢幕解析度換算成視窗的位置與大小。"""
    x = round(screen_width * LEFT_PCT)
    y = round(screen_height * TOP_PCT)
    width = round(screen_width * RIGHT_PCT) - x
    height = round(screen_height * BOTTOM_PCT) - y

    # 螢幕太小的時候，百分比會算出一個小到沒辦法用的視窗。
    # 這時候讓可讀性贏過百分比，但**不能撐出螢幕外** —— 標題列跑到畫面外
    # 就抓不回來了，那比視窗小更糟。
    width = max(width, min(MIN_WIDTH, screen_width))
    height = max(height, min(MIN_HEIGHT, screen_height))
    x = max(0, min(x, screen_width - width))
    y = max(0, min(y, screen_height - height))

    return Box(width=max(1, width), height=max(1, height), x=x, y=y)


def shrink_for_frame(box: Box, frame_width: int, frame_height: int) -> Box:
    """把標題列與邊框的厚度從內容區扣掉。

    `geometry()` 給 tkinter 的是**內容區**的尺寸，Windows 會再往外加標題列
    與邊框。所以照 84% 算出來的高度，實際看到的那個框下緣會落在 91% 左右，
    多出來的就是標題列。

    要讓**看得到的邊界**真的落在 3%~87%，得先扣掉外框。外框有多厚只有在
    視窗實際開出來之後才量得到，所以這裡收的是量好的數字，函式本身仍是純的。

    量錯（例如視窗還沒 realize，量到一個荒謬的值）的時候不能收出一個沒有
    內容的視窗，所以留一個下限。
    """
    if frame_width <= 0 and frame_height <= 0:
        return box
    return Box(
        width=max(MIN_FRAME_REMAINDER, box.width - max(0, frame_width)),
        height=max(MIN_FRAME_REMAINDER, box.height - max(0, frame_height)),
        x=box.x,
        y=box.y,
    )
