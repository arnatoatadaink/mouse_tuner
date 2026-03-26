# Mouse Tuner

Windows のマウス設定を**再起動なしで即時反映**するリアルタイム調整ツール。

## 機能

### タブ1: 基本設定
| 項目 | API | 説明 |
|------|-----|------|
| ポインタ速度 | `SPI_SETMOUSESPEED` | 1〜20 (コントロールパネルと同値) |
| 加速レベル | `SPI_SETMOUSE[2]` | 0=なし / 1=×2 / 2=×4 |
| Threshold 1 | `SPI_SETMOUSE[0]` | 0〜200 mickey/tick (1段階加速の閾値) |
| Threshold 2 | `SPI_SETMOUSE[1]` | 0〜200 mickey/tick (2段階加速の閾値) |

### タブ2: スムーズカーブ
`HKCU\Control Panel\Mouse` の `SmoothMouseXCurve` / `SmoothMouseYCurve` を編集。  
Windows の「ポインターの精度を高める」に相当するベジェ曲線。  
**加速レベル 1 以上のとき有効。**

- 5制御点の Y 値（速度倍率 0.0〜5.0）をスライダー + Spinbox で調整
- キャンバスでリアルタイムプレビュー
- プリセット: Windows既定 / フラット / リニア / アグレッシブ

### 共通ボタン
| ボタン | 動作 |
|--------|------|
| ✓ 即時適用 | 現在の全設定を適用（Registry への書き込みなし） |
| 💾 永続保存 | Registry に書き込み（再起動後も維持） |
| ↩ 元に戻す | 起動時の値にすべて戻す |

## 動作要件

- Windows 10 / 11
- Python 3.8+
- 追加パッケージ不要（標準ライブラリのみ）

## 実行

```bash
python mouse_tuner.py
```

## 技術メモ

### SmoothMouseCurve の固定小数点フォーマット
Registry に格納される 40 バイト = 5点 × 8 バイト。  
各 8 バイトは 64bit 固定小数点（リトルエンディアン）:

```
[fractional 4B LE][integer 4B LE]
```

例: `1.5` → `lo=0x80000000, hi=0x00000001` → `00 00 00 80 01 00 00 00`

### 即時反映の仕組み
1. Registry に書き込む
2. `SystemParametersInfo(SPI_SETMOUSE, ..., SPIF_SENDCHANGE)` で  
   `WM_SETTINGCHANGE` をブロードキャスト → 再起動不要

### 1 mickey の定義
マウスが物理的に **1/200 インチ**動いた量。  
Threshold は「何 mickey/tick 以上で加速を掛けるか」の閾値。
