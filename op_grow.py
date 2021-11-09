import bpy
import bmesh
import math
from mathutils import Vector, kdtree, noise

class DiffGrowthStepOperator(bpy.types.Operator):
    bl_label = "Diff Growth Step"
    bl_idname="object.diff_growth_step"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        obj = context.object
        settings = obj.diff_growth_settings
        bm = bmesh.new()
        bm.from_mesh(obj.data)

        grow_step(
            obj,
            bm,
            seed=settings.seed,
            collision_radius=settings.collision_radius,
            split_radius=settings.split_radius,
            dt=settings.dt,
            weight_decay=settings.weight_decay,
            noise_scale=settings.noise_scale,
            fac_attr=settings.fac_attr,
            fac_rep=settings.fac_rep,
            fac_noise=settings.fac_noise,
        )

        bm.to_mesh(obj.data)
        bm.free()
        obj.data.update()
        return {'FINISHED'}


def grow_step(
    obj,
    bm,
    seed,
    collision_radius,
    split_radius,
    dt,
    weight_decay,
    noise_scale,
    fac_attr,
    fac_rep,
    fac_noise,
):
    group_index = obj.vertex_groups.active_index
    seed_vector = Vector((0, 0, 1)) * seed;

    # Collect vertices with weights
    verts = []
    edges = set()

    for vert in bm.verts:
        weight = get_vertex_weight(bm, vert, group_index)
        if weight > 0:
            verts.append(vert)
            for edge in vert.link_edges:
                edges.add(edge)

    kd = kdtree.KDTree(len(bm.verts))
    for i, vert in enumerate(bm.verts):
        kd.insert(vert.co, i)
    kd.balance()

    # Calc forces
    for vert in verts:
        weight = get_vertex_weight(bm, vert, group_index)
        if weight == 0:
            continue
        f_attr = calc_vert_attraction(vert)
        f_rep = calc_vert_repulsion(vert, kd, collision_radius)
        f_noise = noise.noise_vector(vert.co * noise_scale + seed_vector)
        # print('%s %s %s' % (f_attr, f_rep, f_noise))
        force = \
            fac_attr * f_attr + \
            fac_rep * f_rep + \
            fac_noise * f_noise;
        offset = force * dt * dt * weight;
        vert.co += offset

    # Readjust weights
    for i, vert in enumerate(bm.verts):
        w = get_vertex_weight(bm, vert, group_index)
        w = w ** weight_decay;
        set_vertex_weight(bm, vert, group_index, w)

    # Subdivide
    edges_to_subdivide = []
    for edge in edges:
        avg_weight = calc_avg_edge_weight(bm, [edge], group_index)
        if avg_weight == 0:
            continue
        l = edge.calc_length()
        if (l / split_radius) > (1 / avg_weight):
            edges_to_subdivide.append(edge)

    if len(edges_to_subdivide) > 0:
        print("Subdividing %i" % len(edges_to_subdivide))
        bmesh.ops.subdivide_edges(
            bm,
            edges=edges_to_subdivide,
            smooth=1.0,
            cuts=1,
            use_grid_fill=True,
            use_single_edge=True,)

def get_vertex_weight(bm, vert, group_index):
    weight_layer = bm.verts.layers.deform.active
    weights = vert[weight_layer]
    return weights[group_index] if group_index in weights else 0

def set_vertex_weight(bm, vert, group_index, weight):
    weight_layer = bm.verts.layers.deform.active
    weights = vert[weight_layer]
    weights[group_index] = weight

def calc_avg_edge_length(edges):
    sum = 0.0
    for edge in edges:
        sum += edge.calc_length()
    return sum / len(edges)

def calc_min_edge_length(edges):
    val = 100000
    for edge in edges:
        val = min(edge.calc_length(), val)
    return val

def calc_avg_edge_weight(bm, edges, group_index):
    sum = 0.0
    n = 0
    for edge in edges:
        for vert in edge.verts:
            sum += get_vertex_weight(bm, vert, group_index)
            n += 1
    return sum / n

def calc_vert_attraction(vert):
    result = Vector()
    for edge in vert.link_edges:
        other = edge.other_vert(vert)
        if other == None:
            continue
        result += other.co - vert.co
    return result

def calc_vert_repulsion(vert, kd, radius):
    result = Vector()
    for (co, index, distance) in kd.find_range(vert.co, radius * 2):
        if (index == vert.index):
            continue;
        direction = (vert.co - co).normalized()
        magnitude = math.exp(distance - radius)
        # magnitude = distance
        result += direction * magnitude
    return result;
