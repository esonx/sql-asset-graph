

import datetime

class TimestampShortener:


    _BASE62_CHARS = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
    _BASE = len(_BASE62_CHARS)
    _STRATEGY_PREFIX = {
        'unix': 'U',
        'full': 'F'
    }
    _PREFIX_STRATEGY = {v: k for k, v in _STRATEGY_PREFIX.items()}

    @staticmethod
    def _to_base62(n: int) -> str:

        if n == 0:
            return TimestampShortener._BASE62_CHARS[0]

        res = []
        while n > 0:
            n, rem = divmod(n, TimestampShortener._BASE)
            res.append(TimestampShortener._BASE62_CHARS[rem])

        return "".join(reversed(res))

    @staticmethod
    def _from_base62(s: str) -> int:

        n = 0
        for char in s:
            n = n * TimestampShortener._BASE + TimestampShortener._BASE62_CHARS.index(char)
        return n

    @classmethod
    def encode(cls, timestamp_str: str, strategy: str = 'unix') -> str:


        if strategy not in cls._STRATEGY_PREFIX:
            raise ValueError(f"无效的策略: {strategy}. 可选值为 'unix' 或 'full'。")

        prefix = cls._STRATEGY_PREFIX[strategy]

        if strategy == 'unix':
            try:
                dt_obj = datetime.datetime.strptime(timestamp_str, '%Y%m%d%H%M%S')
                unix_ts = int(dt_obj.replace(tzinfo=datetime.timezone.utc).timestamp())
                return prefix + cls._to_base62(unix_ts)
            except ValueError:
                raise ValueError("无效的时间戳格式, 'unix' 策略需要 'YYYYMMDDHHMMSS' 格式。")
        else:
            try:
                full_int = int(timestamp_str)
                return prefix + cls._to_base62(full_int)
            except (ValueError, TypeError):
                raise ValueError("无效的时间戳格式, 'full' 策略需要一个数字字符串。")

    @classmethod
    def decode(cls, short_id: str) -> int:


        prefix = short_id[0]
        if prefix not in cls._PREFIX_STRATEGY:
            raise ValueError(f"无效的前缀: '{prefix}'. ID应由本类的 encode 方法生成。")

        payload = short_id[1:]
        return cls._from_base62(payload)

    @classmethod
    def decode_to_datetime(cls, short_id: str) -> datetime.datetime:


        if not short_id.startswith(cls._STRATEGY_PREFIX['unix']):
            raise ValueError("此方法仅适用于使用 'unix' 策略编码的ID。")

        unix_ts = cls.decode(short_id)
        return datetime.datetime.fromtimestamp(unix_ts, tz=datetime.timezone.utc)


