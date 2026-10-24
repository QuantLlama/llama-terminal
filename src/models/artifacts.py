"""Ordered feature contract shared by training and inference (no heavy imports)."""

# Keep the training order stable: prediction index zero is the close log return.
FEATURE_COLS = [
    'Log_Ret_Close', 'Log_Ret_High', 'Log_Ret_Low', 'Log_Vol',
    'RSI', 'ADX', 'ATR', 'EMA',
]


def validate_features(config, scaler, state):
    """Validate explicit order, or the historical canonical-eight producer format."""
    names = getattr(scaler, 'feature_names_in_', None)
    if 'feature_cols' in config:
        cols = config['feature_cols']
    elif names is not None:
        cols = list(names)
    else:
        # The old producer fit NumPy arrays in FEATURE_COLS order and saved no
        # feature metadata. Preserve that convention only if all widths agree
        # below; never infer a different schema from a seven-column artifact.
        cols = list(FEATURE_COLS)
    if cols != FEATURE_COLS:
        raise ValueError('Incompatible artifact feature order: expected canonical feature_cols; retrain unsupported orders')
    width = len(cols)
    if 'input_dim' in config and (type(config['input_dim']) is not int or config['input_dim'] != width):
        raise ValueError('Incompatible artifact input_dim: does not match feature_cols')
    if getattr(scaler, 'n_features_in_', None) != width:
        raise ValueError('Incompatible artifact scaler width: does not match feature_cols')
    if names is not None and list(names) != cols:
        raise ValueError('Incompatible artifact scaler feature order: does not match feature_cols')
    for key, axis in (('lstm.weight_ih_l0', 1), ('linear.0.weight', 0), ('linear.0.bias', 0)):
        tensor = state.get(key)
        if tensor is None or len(tensor.shape) <= axis or tensor.shape[axis] != width:
            raise ValueError(f'Incompatible artifact checkpoint width: {key} does not match feature_cols')
    return list(cols)


def feature_metadata(scaler, state):
    """Validate newly trained artifacts before any files are persisted."""
    metadata = dict(feature_cols=list(FEATURE_COLS), input_dim=len(FEATURE_COLS))
    validate_features(metadata, scaler, state)
    return metadata
