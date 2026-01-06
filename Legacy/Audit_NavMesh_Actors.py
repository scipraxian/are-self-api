import unreal

def audit_navmesh_actors():
    print("=" * 50)
    print("   NAVMESH ACTOR AUDIT")
    print("=" * 50)

    # 1. Get all actors (Requires World Partition Cells to be LOADED)
    all_actors = unreal.EditorLevelLibrary.get_all_level_actors()
    
    # 2. Filter for RecastNavMesh
    nav_meshes = [a for a in all_actors if isinstance(a, unreal.RecastNavMesh)]
    
    print(f"Total RecastNavMesh Actors Found: {len(nav_meshes)}")
    print("-" * 50)

    for i, nm in enumerate(nav_meshes):
        label = nm.get_actor_label()
        name = nm.get_name()
        
        # 3. Get Data Layers
        # Note: In 5.1+, this property is 'data_layer_assets'
        try:
            layers = nm.get_editor_property("data_layer_assets")
            layer_names = [layer.get_name() for layer in layers] if layers else ["(Persistent Level)"]
        except Exception:
            layer_names = ["<Error Reading Layers>"]

        # 4. Get Agent Props to ID the specific config
        # Note: We can guess the agent based on Radius/Height
        try:
            radius = nm.get_editor_property("agent_radius")
            height = nm.get_editor_property("agent_height")
            config_id = f"R:{radius:.1f} H:{height:.1f}"
        except Exception:
            config_id = "Unknown Config"

        print(f"#{i+1}: {label} ({name})")
        print(f"    > Agent Profile: {config_id}")
        print(f"    > Location:      {nm.get_actor_location()}")
        print(f"    > Data Layers:   {', '.join(layer_names)}")
        print("-" * 50)

    # 5. Analysis
    if len(nav_meshes) > 3:
        print(f"[ALERT] FOUND {len(nav_meshes)} ACTORS. CONFIG EXPECTS 3.")
        print(" > Immediate Action: Delete the actors labeled 'RecastNavMesh-Default' if 'RecastNavMesh-Default-SmallAgent' also exists.")
    elif len(nav_meshes) == 3:
        print("[OK] Actor count matches Configuration (3).")
    else:
        print(f"[WARN] Only found {len(nav_meshes)}. Check unloaded Data Layers?")

if __name__ == '__main__':
    audit_navmesh_actors()