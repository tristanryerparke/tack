"""Rhino-session lifetime for the standalone layer-panel mock."""

import scriptcontext as sc

from layer_like_panel.panel import LayerLikePanel
from layer_like_panel.state import demo_state


_STATE_KEY = "LayerLikePanel.State"
_WINDOW_KEY = "LayerLikePanel.Window"


def open_panel():
    """Show one floating window, retaining its mock tree between launches."""
    window = sc.sticky.get(_WINDOW_KEY)
    if window is not None and window.Visible:
        window.BringToFront()
        return window

    state = sc.sticky.get(_STATE_KEY)
    if state is None:
        state = demo_state()
        sc.sticky[_STATE_KEY] = state

    window = LayerLikePanel(state)
    sc.sticky[_WINDOW_KEY] = window
    window.Show()
    return window
