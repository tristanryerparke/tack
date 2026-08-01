import Rhino


def pick_child_vertex_mode():
    picker = Rhino.Input.Custom.GetOption()
    picker.SetCommandPrompt("Choose Coincident or Pick Vertex for the child")
    picker.AddOption("Coincident")
    picker.AddOption("PickVertex")
    if picker.Get() != Rhino.Input.GetResult.Option:
        return None
    return picker.Option().EnglishName
