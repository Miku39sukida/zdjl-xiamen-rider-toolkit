# zdjl-xiamen-rider-toolkit
Xiamen Delivery Rider Efficiency Toolkit (Auto Sprite Dual-Device Scripts)
Mobile + Tablet Dual-Device Integration, Address Extraction + Auto Navigation in One Step

## 🌐 Languages / 语言 / 言語
[中文 (简体)](README.md) | English | [日本語](README_jp.md)

## 📦 Included Files
| File Name/Type       | Function                    | Device | Storage Path                |
|---------------------|----------------------------|--------|----------------------------|
| README.md           | Documentation              | General| -                          |
| config_webui.py     | Mobile Web Config Service  | Mobile | Any directory (suggested: Documents folder) |
| merchant_alias.json | Xiamen Merchant Alias Config (Meituan POI) | General | **Mobile/Tablet storage root** |
| requirements.txt    | Python Dependencies        | Mobile | Same directory as `config_webui.py` |
| 自动获取取送地址.zjs | Auto Extract Pickup/Delivery Address | Tablet | Auto Sprite script directory |
| 个人跑单专用_竖屏.zjs| Receive address and launch Meituan Navigation | Mobile | Auto Sprite script directory |

## 🚀 Dual-Device Setup Steps
1. **Prerequisites**: Place `merchant_alias.json` in the storage root directory of both mobile and tablet to ensure scripts can read the config
2. **Tablet**: Open Auto Sprite → Import "自动获取取送地址.zjs" → Run script then switch to order page (supports Ele.me/Meituan/UU)
3. **Mobile**:
   - Open Pydroid/Termux → Navigate to `config_webui.py` directory, run: `pip install -r requirements.txt` (first time only)
   - Run: `python config_webui.py` to start config service
   - Browser access `MobileIP:5000` → Verify config loaded successfully (Xiamen local address prefix should appear)
   - Open Auto Sprite → Run "个人跑单专用_竖屏.zjs" → Automatically receive address from tablet and launch Meituan navigation

## ⚙️ Configuration Notes
- Config file must be in storage root directory (no nested folders), otherwise scripts cannot read it
- Can directly open `merchant_alias.json` with text editor to customize Xiamen merchant aliases and address rules
- `config_webui.py` provides Web interface for CRUD operations on config file (merchant aliases, address regex rules, etc.), no need to manually edit JSON

## 📌 Supported Platforms
- **Address Extraction**: Supports Ele.me Crowdsource/UU Running/Meituan Special Delivery
- **Navigation**: Unified call to **Meituan Maps** (delivery-optimized routes, less detours)

## 🗺️ Meituan Maps Entry Tutorial

### Method 1: Channel Zone Entry
On Meituan homepage, swipe down like WeChat to enter channel zone, tap "地图找店" (Map Find Store)

### Method 2: Search Box Entry
On Meituan homepage, tap search box, enter "地图找店" (Map Find Store) to directly enter

### Xiaomei Built-in Meituan Maps Entry
In conversation, say any navigation destination, let AI call the map, tap to enter and navigate anywhere

---

## ❓ Quick Start FAQ
1. **Script not responding?**
   - Check if Auto Sprite has "Floating Window + Accessibility Permission" enabled (these are required for script operation)
   - Confirm order page is in portrait mode (scripts are designed for portrait interface)

2. **Config file not found?**
   - Check if `merchant_alias.json` is in storage root directory (not in subfolder like "Internal Storage", should be directly in "My Phone" root)
   - Restart Auto Sprite and run script again

3. **Python service failed to start?**
   - First run `pip install -r requirements.txt` to install dependencies
   - Ensure mobile doesn't have "Data Limit" enabled (some phones block local service network requests)

4. **Address extraction inaccurate?**
   - Open `merchant_alias.json` to add corresponding merchant aliases (e.g., "XX Convenience Store" → "XX Supermarket")
   - Increase recognition threshold in web config page (default 0.8, can adjust to 0.9 for higher accuracy)

---

## 🤝 Contributing

Welcome to help update config files and improve Xiamen local merchant aliases and address recognition rules!

### How to Contribute

1. **Setup Config Environment**: Refer to mobile setup steps in "🚀 Dual-Device Setup Steps" above (use `config_webui.py` to start config service)

2. **Edit Config File**: Browser access `localhost:5000` or `127.0.0.1:5000`, use Web interface to CRUD config files visually

3. **Submit Updates**: After editing, submit updated `merchant_alias.json` via PR or Issue, contributors will be credited in project acknowledgments

### Config Notes
- **Merchant Aliases**: Add common merchant name variants to improve recognition accuracy (e.g., "XX Convenience Store" → "XX Supermarket")
- **Address Regex**: Supports capture groups (`$1`, `$2`, etc.) for precise handling of complex address formats (e.g., "后浦社区-36")
- **Config Priority**: Web config overrides local JSON, suggest testing on web first then sync to file

Config file updates benefit all users, thank you to every contributor! 🎉

