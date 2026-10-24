"""Type normalization for the two MT5 connector flavours.

The platform runs MT5 in two modes:

* native (Windows/Wine) - ``mt5_native_connector`` returns MetaTrader5 named
  tuples that are read with attribute access (``pos.ticket``, ``tick.bid``);
* cloud (Linux container) - ``mt5_api_connector`` speaks HTTP to the bridge and
  receives plain JSON dicts.

``normalize`` converts the bridge payloads into attribute-accessible objects
while leaving native objects untouched, so one API code path can serve both.
"""


class AttrDict(dict):
    """A dict whose keys are also readable as attributes.

    Missing keys raise ``AttributeError`` (not ``KeyError``) so ``hasattr`` and
    ``getattr(obj, name, default)`` keep behaving like they do on the native
    MetaTrader5 named tuples.
    """

    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError:
            raise AttributeError(name) from None


def normalize(value):
    """Recursively turn dict payloads into ``AttrDict`` objects.

    Native MetaTrader5 objects (named tuples) and every non-container value pass
    through untouched, so normalizing a native connector result is a no-op.
    """
    if hasattr(value, "_asdict"):
        # Native MetaTrader5 object (named tuple): leave as-is.
        return value
    if isinstance(value, dict):
        return AttrDict({key: normalize(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return [normalize(item) for item in value]
    return value


def positions_to_web(positions):
    """Map connector positions (native or bridge) to the web API payload."""
    result = []
    for position in normalize(positions):
        result.append(
            {
                "ticket": getattr(position, "ticket", None),
                "symbol": getattr(position, "symbol", ""),
                "type": "BUY" if getattr(position, "type", None) == 0 else "SELL",
                "volume": getattr(position, "volume", 0),
                "entry_price": getattr(position, "price_open", 0),
                "current_price": getattr(position, "price_current", 0),
                "sl": getattr(position, "sl", 0),
                "tp": getattr(position, "tp", 0),
                "profit": getattr(position, "profit", 0),
                "swap": getattr(position, "swap", 0),
                "comment": getattr(position, "comment", ""),
            }
        )
    return result


def as_list(value):
    """Return a list for list/tuple payloads, otherwise an empty list.

    The bridge answers failed calls with a dict payload ({"detail": ...}), so
    iterating the result blindly turns keys into items and crashes handlers.
    """
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return []


def symbol_is_tradable(symbol):
    """Whether the handler should list a symbol.

    Native MT5 objects carry an accurate ``trade_mode``. Bridge payloads report
    ``trade_mode == 0`` for every symbol the terminal has not selected yet, so
    filtering on it there would hide the whole catalogue from the cloud UI.
    """
    if isinstance(symbol, AttrDict):
        return True
    return (getattr(symbol, "trade_mode", 0) or 0) != 0
