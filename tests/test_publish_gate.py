"""發布閘門：資料沒變就不要動 docs/（ToDo §1 第 6 條、§9 Day 28 第 3 項）。

驗收句：**「連續兩次跑同一天的資料，第二次沒有產生 commit」**。

**這裡有一個兩條硬規定正面對撞的地方，不解掉的話這一項永遠做不到：**

  §5.4 第 1 條：每次發布**重新產生** salt / IV / CEK
  §1  第 6 條：資料沒變就**不 commit**

密文每次都不一樣，是刻意的、也是不能讓步的（IV 重用是 AES-GCM 的致命傷）。
所以拿 `docs/index.html` 去比對「有沒有變」永遠會說「變了」——
每天都會產生一筆內容完全相同、只有隨機數不同的 commit。

解法：**閘門看的是明文的指紋，不是密文。** 明文一樣就整個跳過封裝，
連 docs/ 都不碰。這樣 §5.4 與 §1 就不衝突了 —— 該換的還是每次都換，
只是「要不要換」這件事在封裝之前就決定了。
"""
from __future__ import annotations

from barometer.crypto import envelope
from barometer.pipeline import publish_gate


PLAIN_A = "<h1>總經評分 68.8</h1>"
PLAIN_B = "<h1>總經評分 71.2</h1>"


def test_same_plaintext_gives_the_same_fingerprint():
    assert publish_gate.fingerprint(PLAIN_A) == publish_gate.fingerprint(PLAIN_A)


def test_different_plaintext_gives_a_different_fingerprint():
    assert publish_gate.fingerprint(PLAIN_A) != publish_gate.fingerprint(PLAIN_B)


def test_ciphertext_differs_every_time_even_for_identical_plaintext(tmp_path):
    """這就是為什麼閘門不能看密文 —— 先把這件事釘在測試裡。"""
    mats = [envelope.material_one_lock("pw")]
    a = envelope.seal(PLAIN_A, mats)
    b = envelope.seal(PLAIN_A, mats)
    assert a["content"]["ct"] != b["content"]["ct"]
    assert a["pub_id"] != b["pub_id"]


def test_first_run_always_publishes(tmp_path):
    gate = publish_gate.Gate(tmp_path / "state.json")
    assert gate.should_publish(PLAIN_A).publish is True


def test_second_run_with_identical_data_does_not_publish(tmp_path):
    gate = publish_gate.Gate(tmp_path / "state.json")
    gate.record(PLAIN_A)
    decision = gate.should_publish(PLAIN_A)
    assert decision.publish is False
    assert "沒有變" in decision.reason


def test_changed_data_publishes_again(tmp_path):
    gate = publish_gate.Gate(tmp_path / "state.json")
    gate.record(PLAIN_A)
    assert gate.should_publish(PLAIN_B).publish is True


def test_force_overrides_the_gate(tmp_path):
    """機制本身壞掉的時候要有辦法硬推一次 —— 但要明講是硬推的。"""
    gate = publish_gate.Gate(tmp_path / "state.json")
    gate.record(PLAIN_A)
    decision = gate.should_publish(PLAIN_A, force=True)
    assert decision.publish is True
    assert "強制" in decision.reason


def test_state_survives_a_new_gate_instance(tmp_path):
    """排程是每天一個新行程 —— 狀態必須落地，不能只活在記憶體裡。"""
    path = tmp_path / "state.json"
    publish_gate.Gate(path).record(PLAIN_A)
    assert publish_gate.Gate(path).should_publish(PLAIN_A).publish is False


def test_corrupt_state_file_fails_open_and_publishes(tmp_path):
    """狀態檔壞掉時要**發布**，不要靜靜地什麼都不做。

    漏發一天，畫面停在昨天而且沒有人會知道；多發一天，只是多一筆 commit。
    這兩種錯的代價差很多。
    """
    path = tmp_path / "state.json"
    path.write_text("{ not json", encoding="utf-8")
    assert publish_gate.Gate(path).should_publish(PLAIN_A).publish is True
