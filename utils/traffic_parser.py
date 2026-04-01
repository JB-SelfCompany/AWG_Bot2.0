def parse_traffic_size(size_str: str) -> int:
    """Преобразование строки размера трафика (из вывода awg show) в байты"""
    size_str = size_str.strip()
    size_str = size_str.replace(' received', '').replace(' sent', '')

    parts = size_str.split()
    if len(parts) != 2:
        return 0

    try:
        value = float(parts[0])
    except ValueError:
        return 0

    unit = parts[1].upper()

    multipliers = {
        'B': 1,
        'KIB': 1024,
        'MIB': 1024 ** 2,
        'GIB': 1024 ** 3,
        'TIB': 1024 ** 4,
        'KB': 1000,
        'MB': 1000 ** 2,
        'GB': 1000 ** 3,
        'TB': 1000 ** 4,
    }

    return int(value * multipliers.get(unit, 1))
