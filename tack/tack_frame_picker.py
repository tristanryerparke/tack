import Rhino


def pick_link_mode():
    picker = Rhino.Input.Custom.GetOption()
    picker.SetCommandPrompt("Tack relationship")
    picker.AddOption("CoincidentVertices")
    picker.AddOption("PickVertices")
    if picker.Get() != Rhino.Input.GetResult.Option:
        return None
    return picker.Option().EnglishName
