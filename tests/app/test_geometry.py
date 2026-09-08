"""視窗尺寸（依螢幕解析度換算）。

規格：**由上到下 3%~87%、由左到右 3%~97%。**

所以視窗寬是螢幕的 94%、高是 84%，左上角落在 (3%, 3%)。

寫成純函式而不是直接塞進 View，是為了讓它能離線測 —— 這一段的錯（少算一次
邊界、把 87% 當成高度而不是下緣）在畫面上看起來都「差不多對」，肉眼驗不出來。
"""
from __future__ import annotations

import pytest

from barometer.app import geometry as g


@pytest.mark.parametrize("sw,sh", [
    (1920, 1080), (2560, 1440), (3840, 2160), (1366, 768), (1280, 800),
])
def test_box_matches_the_percentage_spec(sw, sh):
    box = g.window_box(sw, sh)
    assert box.x == round(sw * 0.03)
    assert box.y == round(sh * 0.03)
    assert box.width == round(sw * 0.97) - round(sw * 0.03)
    assert box.height == round(sh * 0.87) - round(sh * 0.03)


def test_edges_land_on_the_specified_percentages():
    """右緣是 97%、下緣是 87% —— 不是「寬 97%、高 87%」。"""
    box = g.window_box(1920, 1080)
    assert box.x + box.width == round(1920 * 0.97)
    assert box.y + box.height == round(1080 * 0.87)


def test_bottom_leaves_room_for_the_taskbar():
    """下緣停在 87%，底下那 13% 是刻意留給工作列的。"""
    box = g.window_box(1920, 1080)
    assert 1080 - (box.y + box.height) == pytest.approx(1080 * 0.13, abs=1)


def test_geometry_string_is_tk_format():
    assert g.window_box(1920, 1080).as_geometry() == "1804x908+58+32"


def test_tiny_screen_still_gives_a_usable_window():
    """小螢幕要撐到最小尺寸，但**撐不過螢幕本身**。

    這一條跟下一條會打架：800 寬的螢幕放不下 900 寬的視窗。
    打架的時候「不能超出螢幕」贏 —— 視窗小還看得到，標題列跑到畫面外
    就抓不回來了。
    """
    sw, sh = 800, 600
    box = g.window_box(sw, sh)
    assert box.width >= min(g.MIN_WIDTH, sw)
    assert box.height >= min(g.MIN_HEIGHT, sh)


def test_tiny_screen_window_still_fits_on_screen():
    """撐到最小尺寸之後也不能超出螢幕，不然標題列會跑到畫面外抓不到。"""
    sw, sh = 800, 600
    box = g.window_box(sw, sh)
    assert box.x >= 0 and box.y >= 0
    assert box.x + box.width <= sw
    assert box.y + box.height <= sh


def test_absurd_screen_size_does_not_crash():
    box = g.window_box(1, 1)
    assert box.width > 0 and box.height > 0


# ---------------- 外框修正 ----------------

def test_shrink_for_frame_keeps_the_outer_edges_on_spec():
    """`geometry()` 設的是**內容區**，Windows 再往外加標題列與邊框。

    所以照 84% 算出來的高度，實際看到的視窗下緣會落在 91% 左右，不是 87%。
    差的那一塊就是標題列。要讓**看得到的那個框**落在 87%，得先把外框的
    厚度扣掉。

    這個修正只有在真的開了視窗、量到外框厚度之後才做得了，所以純函式這邊
    收的是量好的數字。
    """
    box = g.window_box(1920, 1080)
    fixed = g.shrink_for_frame(box, frame_width=8, frame_height=47)
    assert fixed.width == box.width - 8
    assert fixed.height == box.height - 47
    assert (fixed.x, fixed.y) == (box.x, box.y)


def test_shrink_for_frame_is_a_no_op_without_a_frame():
    """無邊框或非 Windows 的情況，量到 0 就不要動它。"""
    box = g.window_box(1920, 1080)
    assert g.shrink_for_frame(box, 0, 0) == box


def test_shrink_for_frame_never_produces_a_useless_window():
    """外框量錯（例如量成比視窗還大）的時候，不能收出一個零高度的視窗。"""
    box = g.window_box(1920, 1080)
    fixed = g.shrink_for_frame(box, frame_width=9999, frame_height=9999)
    assert fixed.width >= g.MIN_FRAME_REMAINDER
    assert fixed.height >= g.MIN_FRAME_REMAINDER
