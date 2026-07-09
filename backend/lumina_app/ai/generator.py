import logging
import re

import anthropic

from lumina_app.ai.planner import ScenePlan
from lumina_app.settings import settings

logger = logging.getLogger(__name__)

VALID_SCENE_BASES = ["Scene", "MovingCameraScene", "ThreeDScene", "ZoomedScene", "SpecialThreeDScene"]
_BASE_ALTERNATION = "|".join(VALID_SCENE_BASES)

SCENE_PATTERNS = {
    "cinematic_zoom": """
CINEMATIC ZOOM DOCUMENTARY — class must extend MovingCameraScene.

This is the main architecture pattern. The camera physically
zooms into each important node like a documentary film.

class ArchitectureNarrativeTour(MovingCameraScene):
    def construct(self):

PHASE 1 — CONSTELLATION VIEW (10 sec):
Draw ALL nodes as small colored dots spread across a wide canvas.
Use LaggedStart with tiny dots appearing like stars:

  all_dots = VGroup()
  for each node:
    dot = Dot(radius=0.06, color=node_color(node.type))
    dot.move_to(community_position(node.community_id))
    # Add tiny random offset within community cluster
    all_dots.add(dot)

  # Draw edges as faint lines BEFORE dots appear
  edges = VGroup()
  for each edge:
    line = Line(
      pos[edge.source], pos[edge.target],
      stroke_width=0.4,
      stroke_opacity=0.2,
      color=WHITE
    )
    edges.add(line)

  self.play(
    LaggedStart(*[GrowFromCenter(d) for d in all_dots],
                lag_ratio=0.02, run_time=3),
  )
  self.play(Create(edges, lag_ratio=0.01), run_time=2)

  # Camera slowly zooms out to reveal the full constellation
  self.play(
    self.camera.frame.animate.scale(1.3),
    run_time=2, rate_func=smooth
  )
  self.wait(1)

PHASE 2 — CINEMATIC ZOOM SEQUENCE (per god node):
For EACH of the top 3-4 god nodes, do this sequence:

  a) SPOTLIGHT APPROACH (3 sec):
     # Draw a pulsing ring around the target node
     target_pos = positions[god_node.id]
     ring = Circle(radius=0.3, color=YELLOW_C, stroke_width=2)
     ring.move_to(target_pos)
     self.play(Create(ring), Flash(all_dots[god_node_idx],
               color=YELLOW_C, flash_radius=0.3))
     self.play(ring.animate.scale(1.5).set_opacity(0),
               run_time=0.8)

     # Dim ALL other dots and edges
     others = VGroup(*[d for k,d in dot_map.items()
                       if k != god_node.id])
     self.play(
       others.animate.set_opacity(0.06),
       edges.animate.set_opacity(0.04),
       run_time=1, rate_func=smooth
     )

  b) CAMERA ZOOM IN (2.5 sec):
     # The camera frame actually zooms to this node
     # This is the KEY cinematic technique - real zoom
     self.play(
       self.camera.frame.animate
         .scale(0.35)  # zoom in tight
         .move_to(target_pos),
       run_time=2.5,
       rate_func=smooth
     )

  c) NODE EXPANSION (1.5 sec):
     # The selected dot expands into a detail card
     # Now visible because camera is zoomed in
     detail = self._build_detail_card(god_node)
     detail.move_to(target_pos)

     self.play(
       all_dots[idx].animate.scale(3).set_color(WHITE),
       FadeIn(detail, shift=UP*0.05),
       run_time=1.5, rate_func=smooth
     )

  d) DETAIL HOLD (3 sec):
     # While zoomed in, animate some details in the card
     self.play(
       LaggedStart(
         *[Write(line) for line in detail.submobjects[2:]],
         lag_ratio=0.3
       )
     )
     self.wait(2)

  e) ZOOM OUT (2 sec):
     # Camera pulls back to constellation view
     self.play(
       FadeOut(detail),
       all_dots[idx].animate.scale(1/3).set_color(original_color),
       run_time=1, rate_func=smooth
     )
     self.play(
       self.camera.frame.animate
         .scale(1/0.35)
         .move_to(ORIGIN),
       others.animate.set_opacity(1.0),
       edges.animate.set_opacity(0.2),
       run_time=2, rate_func=smooth
     )
     self.wait(0.5)

PHASE 3 — PULSE FINALE (5 sec):
After all zoom sequences, show data flowing through the graph:
  # Animate glowing dots traveling along key edges
  for key_edge in top_5_edges:
    traveler = Dot(radius=0.05, color=YELLOW_C)
    traveler.move_to(positions[key_edge.source])
    path = Line(positions[key_edge.source],
                positions[key_edge.target])
    self.play(MoveAlongPath(traveler, path,
              run_time=0.8, rate_func=smooth))

  self.wait(2)

HELPER: _build_detail_card(node) creates a VGroup:
  card background: RoundedRectangle(width=1.8, height=1.1,
    corner_radius=0.06, fill_color=BLACK, fill_opacity=0.9,
    stroke_color=node_color(node.type), stroke_width=0.8)
  title: Text(node.label, font_size=9, color=WHITE)
  type badge: Text(node.type, font_size=7, color=accent)
  file: Text(short_path(node.source_file), font_size=6, color=GRAY_A)
  bullet 1-3: Text based on edges (calls X, used by Y)
  ALL at small font sizes because camera is zoomed in

IMPORTANT: build the card at NORMAL size and position it at the
node — the camera zoom (camera.frame.scale(0.35)) is what makes
it read as large and detailed on screen. Do not pre-shrink it.
""",
    "3d_orbital": """
THREE-D ORBITAL — class must extend ThreeDScene.

The dependency graph as a 3D galaxy. The camera orbits it.

class Architecture3DOrbital(ThreeDScene):
    def construct(self):
        # Set initial camera angle — looking down at an angle
        self.set_camera_orientation(phi=70*DEGREES, theta=-45*DEGREES)

PHASE 1 — 3D GALAXY ASSEMBLY (8 sec):
Position nodes as 3D spheres in space using community clusters:
  - Each community gets a position on a sphere of radius 5
  - Nodes within a community spread in radius 1.5
  - God nodes get larger spheres: Sphere(radius=0.3)
  - Other nodes: Sphere(radius=0.12)

  for node in nodes:
    sphere = Sphere(
      radius=0.25 if is_god_node else 0.1,
      resolution=(8, 8)  # lower res for performance
    )
    sphere.set_color(node_color(node.type))
    sphere.move_to(positions_3d[node.id])
    spheres.append(sphere)

  # Assemble with LaggedStart from center outward
  self.play(
    LaggedStart(*[GrowFromCenter(s) for s in spheres],
    lag_ratio=0.03, run_time=3)
  )

  # Draw edges as 3D Lines
  for edge in edges[:50]:  # limit for performance
    line = Line3D(
      positions_3d[edge.source],
      positions_3d[edge.target],
      thickness=0.005,
      color=WHITE
    ).set_opacity(0.15)
    self.play(Create(line), run_time=0.1)

PHASE 2 — ORBITAL APPROACH (15 sec):
Begin slow ambient rotation so viewer sees the graph in 3D:
  self.begin_ambient_camera_rotation(rate=0.1, about="theta")
  self.wait(5)

  # Swoop toward the biggest god node
  self.stop_ambient_camera_rotation()
  god_pos = positions_3d[god_nodes[0].id]

  self.move_camera(
    phi=60*DEGREES,
    theta=-20*DEGREES,
    zoom=2.5,  # zoom in
    frame_center=god_pos,
    run_time=3,
    rate_func=smooth
  )

  # Flash the god node
  self.play(
    spheres[god_idx].animate.scale(2).set_color(YELLOW_C),
    run_time=1
  )
  self.wait(2)

PHASE 3 — FLY THROUGH (10 sec):
For each god node, fly the camera to it:
  for i, god_node in enumerate(god_nodes[:3]):
    self.move_camera(
      frame_center=positions_3d[god_node.id],
      zoom=2.0 + i*0.3,
      run_time=2.5,
      rate_func=smooth
    )
    self.play(
      Flash(spheres[god_idx_map[god_node.id]],
            color=YELLOW_C, flash_radius=0.5)
    )

    # Show fixed-in-frame label (stays on screen during rotation)
    label = Text(god_node.label, font_size=24, color=WHITE)
    label.to_corner(UL)
    self.add_fixed_in_frame_mobjects(label)
    self.play(FadeIn(label))
    self.wait(1.5)
    self.play(FadeOut(label))
    self.remove_fixed_in_frame_mobjects(label)

PHASE 4 — PULL BACK (5 sec):
  # Pull back to see the full galaxy
  self.move_camera(
    phi=70*DEGREES,
    theta=-45*DEGREES,
    zoom=1.0,
    frame_center=ORIGIN,
    run_time=3,
    rate_func=smooth
  )
  self.begin_ambient_camera_rotation(rate=0.05)
  self.wait(3)
  self.stop_ambient_camera_rotation()
""",
    "data_flow_pulse": """
DATA FLOW PULSE — class extends MovingCameraScene.

Show data flowing through the architecture like electricity.
No static boxes — everything pulses and flows.

class DataFlowPulse(MovingCameraScene):
    def construct(self):

SETUP: Draw components as rounded nodes, sized by importance.
Position them in a flow layout (left to right or top to bottom
based on the request flow: entry point → processing → storage):

  entry_nodes = [routes, API endpoints]  # colored BLUE_C
  process_nodes = [services, classes]    # colored GREEN_C
  storage_nodes = [models, DB]           # colored RED_C

  # Arrange in 3 columns
  for i, node in enumerate(entry_nodes):
    rect = RoundedRectangle(width=2.2, height=0.7,
                            corner_radius=0.15,
                            fill_color=BLUE_E,
                            fill_opacity=0.8)
    label = Text(node.label[:18], font_size=18, color=WHITE)
    label.move_to(rect.get_center())
    group = VGroup(rect, label)
    group.move_to(LEFT*4 + UP*(i - len(entry_nodes)/2)*1.1)

PHASE 1 — NODES APPEAR (5 sec):
  self.play(
    LaggedStart(
      *[GrowFromCenter(n) for n in all_node_groups],
      lag_ratio=0.15, run_time=3
    )
  )

PHASE 2 — CONNECTIONS DRAW (3 sec):
  # Draw curved arrows between related nodes
  for edge in key_edges:
    arrow = CurvedArrow(
      source_pos, target_pos,
      angle=-0.3,
      stroke_width=1.5,
      color=GRAY_A,
      tip_length=0.15
    )
    self.play(GrowArrow(arrow), run_time=0.4)

PHASE 3 — PULSE ANIMATION (15 sec):
This is the key cinematic moment.
Send glowing particles along the edges repeatedly:

  def send_pulse(source, target, color=YELLOW_C):
    # Create a glowing traveling dot
    pulse = Dot(radius=0.08, color=color)
    pulse.add(Circle(radius=0.15, color=color,
                     stroke_opacity=0.3, stroke_width=1))
    pulse.move_to(source)
    path = CubicBezier(source,
                       source + RIGHT*0.5 + UP*0.3,
                       target + LEFT*0.5 + DOWN*0.3,
                       target)
    anim = MoveAlongPath(pulse, path,
                         run_time=0.7,
                         rate_func=smooth)
    return anim, pulse

  # Send multiple pulses along the request flow
  # Repeat 3-4 times to show the flow pattern
  for _ in range(3):
    anims = []
    pulses = []
    # Stagger pulses along the full path
    for i, (src, tgt) in enumerate(flow_pairs):
      anim, pulse = send_pulse(
        node_positions[src],
        node_positions[tgt],
        color=[BLUE_C, GREEN_C, YELLOW_C, RED_C][i % 4]
      )
      anims.append(anim)
      pulses.append(pulse)

    self.play(
      LaggedStart(*anims, lag_ratio=0.3)
    )
    self.play(*[FadeOut(p) for p in pulses], run_time=0.3)
    self.wait(0.5)

PHASE 4 — ZOOM INTO BOTTLENECK (8 sec):
Find the most connected node and zoom into it:
  bottleneck = god_nodes[0]
  self.play(
    self.camera.frame.animate
      .scale(0.4)
      .move_to(node_positions[bottleneck.id]),
    run_time=2, rate_func=smooth
  )

  # Show it handle multiple connections
  self.play(Flash(node_groups[bottleneck.id],
                  color=YELLOW_C, flash_radius=0.8))
  self.wait(2)

  self.play(
    self.camera.frame.animate.scale(2.5).move_to(ORIGIN),
    run_time=2, rate_func=smooth
  )
""",
    "zoomed_reveal": """
ZOOMED REVEAL — class extends ZoomedScene.

Uses Manim's built-in ZoomedScene for picture-in-picture.
The main view shows the full graph.
A magnifying lens follows and zooms into each important node.

class ArchitectureZoomedReveal(ZoomedScene):
    def __init__(self):
        super().__init__(
            zoom_factor=4,
            zoomed_display_height=3,
            zoomed_display_width=4,
            zoomed_display_corner=UR,
            zoom_activated=False,
        )

    def construct(self):

PHASE 1 — FULL GRAPH (5 sec):
Draw the complete dependency graph at small scale.
Nodes, edges, community colors — same as before but SMALL
because the zoom will reveal details.

PHASE 2 — ACTIVATE ZOOM LENS (2 sec):
  # Create zoomed display (picture-in-picture in top-right)
  self.activate_zooming(animate=True)

  # Style the zoom display
  self.zoomed_camera.frame.set_color(YELLOW_C)
  self.zoomed_display.set_stroke(YELLOW_C, 2)

  self.wait(1)

PHASE 3 — SCAN KEY NODES (20 sec):
Move the zoom lens across the graph, pausing at each god node:

  for god_node in god_nodes[:4]:
    target = node_positions[god_node.id]

    # Slide zoom frame to this node
    self.play(
      self.zoomed_camera.frame.animate.move_to(target),
      run_time=1.5, rate_func=smooth
    )

    # The PIP window now shows the node enlarged
    # Highlight it in the main view
    self.play(
      Indicate(node_dots[god_node.id],
               scale_factor=2, color=YELLOW_C)
    )

    # Show label fixed in zoomed display
    label = Text(god_node.label, font_size=20)
    label.next_to(self.zoomed_display, DOWN, buff=0.1)
    label.add_background_rectangle(color=BLACK, opacity=0.8)
    self.play(FadeIn(label))
    self.wait(2)
    self.play(FadeOut(label))

PHASE 4 — DEACTIVATE AND OVERVIEW (5 sec):
  self.play(self.zoomed_camera.frame.animate.scale(3))
  self.wait(2)
""",
    "morphing_network": """
MORPHING NETWORK — class extends Scene with ValueTracker.

The graph morphs between states using ValueTracker and always_redraw.
Edges pulse with animated opacity. Nodes breathe.

class MorphingNetwork(Scene):
    def construct(self):

SETUP:
  # Use ValueTracker to drive continuous animations
  t = ValueTracker(0)

  # All nodes as dots
  node_dots = {}
  for node in nodes:
    dot = always_redraw(lambda n=node:
      Dot(
        radius=0.12 + 0.03 * np.sin(t.get_value() * 2 + hash(n.id) % 10),
        color=node_color(n.type)
      ).move_to(positions[n.id])
    )
    node_dots[node.id] = dot

  # Edges with animated opacity
  edge_lines = []
  for edge in edges[:40]:
    line = always_redraw(lambda e=edge:
      Line(
        positions[e.source], positions[e.target],
        stroke_width=0.6,
        stroke_opacity=0.1 + 0.15 * abs(np.sin(
          t.get_value() * 1.5 + hash(e.source) % 7
        )),
        color=edge_color(e.confidence)
      )
    )
    edge_lines.append(line)

PHASE 1 — ASSEMBLY (5 sec):
  self.add(*edge_lines, *node_dots.values())
  # Animate t to bring everything to life
  self.play(
    LaggedStart(
      *[FadeIn(d) for d in node_dots.values()],
      lag_ratio=0.03
    ),
    t.animate.set_value(TAU),
    run_time=4
  )

PHASE 2 — LIVING NETWORK (10 sec):
  # Continue animating t — network breathes
  self.play(t.animate.set_value(4*TAU), run_time=8,
            rate_func=linear)

PHASE 3 — HIGHLIGHT KEY PATHS (10 sec):
  # Show important connections with glowing travelers
  for god_node in god_nodes[:3]:
    # Find all edges connected to this god node
    connected = [e for e in edges
                 if e.source == god_node.id or
                    e.target == god_node.id][:5]

    # Send pulses along each connection
    for edge in connected:
      src = positions[edge.source]
      tgt = positions[edge.target]
      traveler = Dot(radius=0.07, color=YELLOW_A)
      traveler.move_to(src)
      self.play(
        MoveAlongPath(traveler, Line(src, tgt)),
        node_dots[god_node.id].animate.set_color(YELLOW_C),
        run_time=0.6, rate_func=smooth
      )
      self.remove(traveler)

    self.play(node_dots[god_node.id].animate
              .set_color(node_color(god_node.type)))

PHASE 4 — FADE WITH TITLE (5 sec):
  title = Text("Explore project-docs/ for details",
               font_size=24, color=WHITE)
  title.add_background_rectangle(color=BLACK, opacity=0.7)
  title.to_edge(DOWN)
  self.play(FadeIn(title), t.animate.set_value(6*TAU),
            run_time=3)
  self.wait(2)
""",
    "folder_deep_dive": """
FOLDER DEEP DIVE — class extends MovingCameraScene.

For per-folder videos. Camera starts wide showing where
this folder sits in the full system, then zooms into
the folder's internals.

class BackendFolderOverview(MovingCameraScene):
    def construct(self):

PHASE 1 — SYSTEM CONTEXT (8 sec):
Show simplified view of ALL top-level folders as nodes:
  # Each folder = a rounded rectangle
  # This folder = highlighted, others = dimmed

  folder_nodes = {}
  for folder in all_folders:
    rect = RoundedRectangle(
      width=2.0, height=0.8, corner_radius=0.12,
      fill_color=(PURPLE_E if folder == THIS_FOLDER
                  else DARK_GRAY),
      fill_opacity=0.9
    )
    label = Text(folder + "/", font_size=18,
                 color=(WHITE if folder == THIS_FOLDER
                        else GRAY_A))
    label.move_to(rect.get_center())
    group = VGroup(rect, label)
    folder_nodes[folder] = group

  # Arrange in circle or grid
  # Draw connection lines between folders

  # Animate appearing
  self.play(
    LaggedStart(*[FadeIn(n) for n in folder_nodes.values()],
    lag_ratio=0.2)
  )

  # Flash THIS folder to draw attention
  self.play(
    folder_nodes[THIS_FOLDER].animate.scale(1.3),
    Flash(folder_nodes[THIS_FOLDER], color=PURPLE_C)
  )
  self.play(folder_nodes[THIS_FOLDER].animate.scale(1/1.3))
  self.wait(1)

PHASE 2 — ZOOM INTO FOLDER (3 sec):
  # Camera zooms into THIS folder
  self.play(
    self.camera.frame.animate
      .scale(0.5)
      .move_to(folder_nodes[THIS_FOLDER].get_center()),
    run_time=2.5, rate_func=smooth
  )

PHASE 3 — FOLDER INTERNALS REVEAL (15 sec):
  # Fade out the folder overview
  self.play(*[FadeOut(n) for n in folder_nodes.values()])

  # Reset camera
  self.play(
    self.camera.frame.animate.scale(2).move_to(ORIGIN),
    run_time=1, rate_func=smooth
  )

  # Now show the files inside this folder
  # as a mini graph with real relationships
  for file in folder_files[:8]:
    node = RoundedRectangle(width=2.5, height=0.65,
                            corner_radius=0.1,
                            fill_color=file_color(file.language),
                            fill_opacity=0.85)
    name = Text(basename(file.path), font_size=16, color=WHITE)
    name.move_to(node.get_center())
    file_nodes[file.path] = VGroup(node, name)

  # Arrange file nodes
  # Show them appearing one by one
  self.play(
    LaggedStart(*[Create(n) for n in file_nodes.values()],
    lag_ratio=0.25, run_time=3)
  )

  # Draw intra-folder edges (calls, imports)
  for edge in folder_internal_edges:
    arrow = Arrow(
      file_nodes[edge.source].get_right(),
      file_nodes[edge.target].get_left(),
      stroke_width=1.5, buff=0.1,
      color=relation_color(edge.relation)
    )
    label = Text(edge.relation, font_size=12, color=GRAY_A)
    label.move_to(arrow.get_center() + UP*0.15)
    self.play(GrowArrow(arrow), FadeIn(label), run_time=0.5)

  # Zoom into the most important file
  key_file = folder_god_node
  self.play(
    self.camera.frame.animate
      .scale(0.5)
      .move_to(file_nodes[key_file].get_center()),
    run_time=2, rate_func=smooth
  )
  self.play(
    Flash(file_nodes[key_file], color=WHITE, flash_radius=0.8)
  )
  self.wait(2)

  # Pull back
  self.play(
    self.camera.frame.animate.scale(2).move_to(ORIGIN),
    run_time=1.5, rate_func=smooth
  )

PHASE 4 — EXTERNAL CONNECTIONS (8 sec):
  # Show how this folder connects to the rest
  # Bring back simplified other folders
  # Draw arrows from this folder out to them
  self.wait(1)

PHASE 5 — OUTRO (5 sec):
  outro = Text("See docs/{folder}/README.md",
               font_size=22, color=GRAY_A)
  outro.to_edge(DOWN)
  self.play(FadeIn(outro))
  self.wait(3)
  self.play(FadeOut(outro))
""",
    "multi_scene_cinematic": """
MULTI-SCENE CINEMATIC — generates multiple Scene classes.
Each uses the cinematic techniques above.

Generate a Python file with THESE specific classes
(rename based on actual codebase content):

class ProjectTitleCard(Scene):
    # Bold title animation
    # Project name in large font, animated with Write()
    # Subtitle fades in
    # Technology badges appear as colored pills
    # Duration: 10 sec

class SystemGalaxy(ThreeDScene):
    # USE the 3d_orbital pattern above
    # Folders/major components as 3D spheres
    # Camera orbits, then flies to key components
    # Duration: 30-40 sec

class RequestJourneyFlow(MovingCameraScene):
    # USE the data_flow_pulse pattern above
    # Show complete request: entry → auth → quota → process → store
    # Pulses travel along the edges
    # Camera zooms into bottleneck node
    # Duration: 25-35 sec

class ComponentDeepDive(MovingCameraScene):
    # USE the cinematic_zoom pattern above
    # For each of 3 god nodes: zoom in, show details, zoom out
    # Duration: 30-40 sec

class DocsOutro(Scene):
    # List generated documentation
    # "project-docs/" as a file tree appearing line by line
    # Links to each document type
    # Duration: 8 sec

TOTAL: 100-130 seconds of cinematic architecture storytelling.
""",
}

LAYOUT_RULES = """
LAYOUT RULES:
- 2D frame: 14.2 wide × 8 tall units
- Content area: y from -3.5 to 3.5
- For MovingCameraScene: camera.frame can go anywhere,
  so build content at reasonable scale, camera zooms in
- For ThreeDScene: use OUT/IN for depth,
  3D positions can extend further (radius 5-8 for galaxy)
- Text font_size: 16-36 (smaller for zoomed scenes)
- Never place HUD text (fixed_in_frame) below y=-3
"""


def _scene_pattern_key(scene_name: str, description: str) -> str:
    """Pick which SCENE_PATTERNS entry best fits this scene.

    Checked in order of specificity: "multi"/"complete"/"full"/"narrative"
    scene names always route to the multi-class cinematic pattern first,
    since a plan like "CompleteArchitectureOverview" would otherwise also
    match the "architecture" keyword used for the (single-class) 3D
    orbital pattern below. Folder deep-dive names are checked next for the
    same reason — "BackendFolderOverview" contains "overview"-adjacent
    text that isn't a routing signal here.
    """
    name = scene_name.lower()
    desc = description.lower()

    if any(w in name for w in ["complete", "full", "multi", "narrative"]):
        return "multi_scene_cinematic"

    if "folderoverview" in name or "folder" in name:
        return "folder_deep_dive"

    if any(w in name + desc for w in ["flow", "pipeline", "request", "journey", "pulse"]):
        return "data_flow_pulse"

    if any(w in name + desc for w in ["architecture", "galaxy", "orbital", "3d"]):
        return "3d_orbital"

    if any(w in name + desc for w in ["tour", "zoom", "documentary", "spotlight"]):
        return "cinematic_zoom"

    if any(w in name + desc for w in ["model", "schema", "class", "morph", "network"]):
        return "morphing_network"

    return "cinematic_zoom"


def _get_scene_pattern(scene_name: str, description: str) -> str:
    """Pick the most relevant visual pattern for this scene."""
    return SCENE_PATTERNS[_scene_pattern_key(scene_name, description)]


def _extract_text(message) -> str:
    """Return the first text block's content.

    claude-sonnet-5 runs adaptive thinking by default, so content[0] is
    often a `thinking` block rather than the answer — content[0].text is
    then None, not a "no response" signal. Find the first block that's
    actually type=="text" instead of assuming position 0.
    """
    for block in message.content:
        if block.type == "text":
            return block.text
    return ""


def _strip_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:])
    if text.endswith("```"):
        text = text[: text.rfind("```")]
    return text.strip()


def _fallback_scene(scene_name: str, title: str) -> str:
    return f'''from manim import *

class {scene_name}(Scene):
    def construct(self):
        title = Text("{title}", font_size=36)
        self.play(Write(title))
        self.wait(1)
        self.play(FadeOut(title))
        self.wait(0.5)
'''


async def generate_scene(
    plan: ScenePlan,
    summaries: dict[str, str],
    graph: dict,
    custom_instructions: str | None = None,
) -> str:
    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])

    relevant_nodes = [n for n in nodes if n["source_file"] in plan.relevant_files]
    key_classes = [n["label"] for n in relevant_nodes if n["type"] == "class"][:5]
    key_functions = [n["label"] for n in relevant_nodes if n["type"] in ("function", "method")][:5]
    key_routes = [n["label"] for n in relevant_nodes if n["type"] == "route"][:5]

    relevant_edges = [
        e
        for e in edges
        if any(e["source"].startswith(f) or e["target"].startswith(f) for f in plan.relevant_files)
        and e["relation"] in ("calls", "inherits", "handles", "implements")
    ]
    edge_str = "\n".join(
        f"  {e['source'].split('::')[-1]} "
        f"--{e['relation']}--> "
        f"{e['target'].split('::')[-1]}"
        for e in relevant_edges[:10]
    )

    relevant_summaries = "\n".join(
        f"  {f}: {summaries.get(f, 'No summary available')}" for f in plan.relevant_files
    )

    user_message = f"""Scene: {plan.scene_name}
Title: {plan.title}
Description: {plan.description}

File summaries:
{relevant_summaries}

Key classes: {', '.join(key_classes) or 'none'}
Key functions: {', '.join(key_functions) or 'none'}
Key routes: {', '.join(key_routes) or 'none'}

Key relationships:
{edge_str or '  (none found)'}"""

    pattern_key = _scene_pattern_key(plan.scene_name, plan.description)
    pattern = SCENE_PATTERNS[pattern_key]
    is_multi_scene = pattern_key == "multi_scene_cinematic"
    # A multi-scene file needs 5+ Scene classes worth of code — 10000
    # tokens is enough for one scene but risks truncating (and thus
    # failing compile()) a full multi-scene response.
    max_tokens = 16000 if is_multi_scene else 10000

    class_rule = (
        "- Generate AT LEAST 3 Scene-based classes (5+ recommended — see VISUAL "
        "PATTERN below for suggested roles), each named descriptively for what it "
        "shows, each with its own construct() and no shared state"
        if is_multi_scene
        else f"- Class name must be exactly: {plan.scene_name}"
    )

    system = f"""You are a Manim CE cinematic animation expert.
Generate professional, modern Manim animations using advanced
scene types and cinematic techniques.

{"Generate a COMPLETE multi-class Python file." if is_multi_scene else "Generate ONE Scene class."}

CRITICAL MANIM RULES:
- Output ONLY valid Python code. Zero markdown. Zero backticks.
- First line: from manim import *
- NEVER use MathTex or Tex — ONLY Text()
- Keep text labels under 20 characters
{class_rule}
- End every construct() with self.wait(1)

SCENE TYPE SELECTION:
{"- Inherit from MovingCameraScene for zoom/pan cinematics" if pattern_key in ("cinematic_zoom", "data_flow_pulse", "folder_deep_dive") else ""}
{"- Inherit from ThreeDScene for 3D perspective" if pattern_key == "3d_orbital" else ""}
{"- Inherit from Scene with ValueTracker for morphing" if pattern_key == "morphing_network" else ""}
{"- Use ZoomedScene for picture-in-picture" if pattern_key == "zoomed_reveal" else ""}

CINEMATIC TECHNIQUES TO USE:
1. CAMERA MOVEMENT (MovingCameraScene):
   self.camera.frame.animate.scale(0.4).move_to(target_pos)
   — This creates REAL zoom, not just scaling objects

2. 3D CAMERA (ThreeDScene):
   self.set_camera_orientation(phi=70*DEGREES, theta=-45*DEGREES)
   self.move_camera(phi=60*DEGREES, zoom=2.0, run_time=2)
   self.begin_ambient_camera_rotation(rate=0.08)
   self.add_fixed_in_frame_mobjects(text)  # HUD text

3. FLOWING DATA:
   pulse = Dot(radius=0.06, color=YELLOW_C)
   self.play(MoveAlongPath(pulse, path, run_time=0.7))

4. LIVING ANIMATIONS:
   t = ValueTracker(0)
   element = always_redraw(lambda:
     Dot(radius=0.1 + 0.02*np.sin(t.get_value())))
   self.play(t.animate.set_value(TAU*3), run_time=5)

5. SMOOTH EASING:
   rate_func=smooth on ALL camera movements and transitions
   Use lag_ratio for staggered group appearances

6. ATTENTION:
   Flash(object, color=YELLOW_C, flash_radius=0.5)
   Indicate(object, scale_factor=1.5, color=YELLOW_C)
   Circumscribe(object, color=WHITE)

TIMING:
{"- Total duration: 100-130 seconds across all scenes" if is_multi_scene else "- Total duration: 30-60 seconds"}
- Use self.wait(1.5-3) between major beats
- Camera moves: run_time=2-3, rate_func=smooth
- Object appearances: LaggedStart with lag_ratio=0.05-0.2
- Pulses: run_time=0.5-0.8, rate_func=smooth

LAYOUT (2D scenes):
{LAYOUT_RULES}
VISUAL PATTERN TO FOLLOW:
{pattern}

CONTEXT (use actual names from this):
Scene: {plan.scene_name}
Focus: {plan.description}

Files involved: {', '.join(plan.relevant_files[:5])}
Key classes: {', '.join(key_classes)}
Key functions: {', '.join(key_functions)}
Key routes: {', '.join(key_routes)}

Relationships:
{edge_str or '  (none found)'}
"""

    if custom_instructions:
        system += f"\n\nUser's custom requirements:\n{custom_instructions}"

    for attempt in range(2):
        try:
            client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
            message = await client.messages.create(
                model=settings.anthropic_model_smart,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": user_message}],
            )
            code = _strip_fences(_extract_text(message))
            logger.debug(
                "Generated code for %s (%d chars, attempt %d):\n%s...",
                plan.scene_name, len(code), attempt + 1, code[:500],
            )
            if is_multi_scene:
                scene_classes = re.findall(
                    rf"class\s+\w+\s*\(\s*(?:{_BASE_ALTERNATION})\s*\)", code
                )
                if len(scene_classes) < 3:
                    # Need at least 3 scene classes for a multi-scene video
                    logger.warning(
                        "Multi-scene validation failed: only found %d scene classes. Retrying...",
                        len(scene_classes),
                    )
                    continue
            else:
                name_pattern = re.compile(
                    rf"class\s+{re.escape(plan.scene_name)}\s*\(\s*(?:{_BASE_ALTERNATION})\s*\)"
                )
                if not name_pattern.search(code):
                    # Scene name (or a valid cinematic base class) not found — retry once
                    logger.warning(
                        "Scene name validation failed: '%s' not in generated code. First 200 chars: %s",
                        plan.scene_name, code[:200],
                    )
                    continue
            try:
                compile(code, f"<scene:{plan.scene_name}>", "exec")
            except SyntaxError as e:
                # Response likely got truncated by max_tokens — retry once
                logger.warning(
                    "Syntax error in generated code for %s: %s. Line %s: %s",
                    plan.scene_name, e, e.lineno, e.text,
                )
                continue
            return code
        except Exception:
            break

    return _fallback_scene(plan.scene_name, plan.title)
