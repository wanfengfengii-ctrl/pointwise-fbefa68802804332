from dataclasses import dataclass
from fractions import Fraction
from itertools import product

from issue.evidence import StationEvidence, Vector, affine_frame


@dataclass(frozen=True)
class LinearBound:
    coefficients: Vector
    limit: Fraction
    strict: bool = False

    def residual(self, point: Vector) -> Fraction:
        return sum(weight * value for weight, value in zip(self.coefficients, point)) - self.limit


@dataclass(frozen=True)
class ReadForm:
    constant: Fraction
    coefficients: Vector


@dataclass(frozen=True)
class _Vertex:
    point: Vector
    faces: int


@dataclass(frozen=True)
class _Region:
    vertices: tuple[_Vertex, ...]
    next_face: int
    strict_bounds: tuple[LinearBound, ...] = ()

    def _clip(self, bound: LinearBound):
        dimension = len(self.vertices[0].point)
        if len(bound.coefficients) != dimension:
            raise ValueError('linear bound has the wrong coordinate dimension')
        residuals = tuple(bound.residual(vertex.point) for vertex in self.vertices)
        if max(residuals) <= 0:
            return self
        if min(residuals) > 0:
            return None

        face = 1 << self.next_face
        kept = []
        inside = []
        outside = []
        for index, (vertex, residual) in enumerate(zip(self.vertices, residuals)):
            if residual < 0:
                kept.append(vertex)
                inside.append(index)
            elif residual == 0:
                kept.append(_Vertex(vertex.point, vertex.faces | face))
            else:
                outside.append(index)

        face_masks = tuple(vertex.faces for vertex in self.vertices)
        for inside_index in inside:
            for outside_index in outside:
                common = face_masks[inside_index] & face_masks[outside_index]
                if common.bit_count() < dimension - 1:
                    continue
                # Tight constraints shared by both vertices define their
                # smallest common face. Exactly two vertices make it an edge.
                if any(mask & common == common for index, mask in enumerate(face_masks)
                       if index != inside_index and index != outside_index):
                    continue
                a = residuals[inside_index]
                b = residuals[outside_index]
                fraction = a / (a - b)
                start = self.vertices[inside_index].point
                end = self.vertices[outside_index].point
                point = tuple(x + fraction * (y - x) for x, y in zip(start, end))
                kept.append(_Vertex(point, common | face))
        return _Region(tuple(kept), self.next_face + 1, self.strict_bounds)

    def restrict(self, bounds: tuple[LinearBound, ...]):
        region = self
        strict = self.strict_bounds
        for bound in bounds:
            region = region._clip(bound)
            if region is None:
                return None
            if bound.strict:
                strict += (bound,)
        # The average of all remaining vertices satisfies every strict bound
        # precisely when each such bound has at least one slack vertex.
        if any(not any(bound.residual(vertex.point) < 0 for vertex in region.vertices)
               for bound in strict):
            return None
        return _Region(region.vertices, region.next_face, strict)


@dataclass(frozen=True)
class ProductDomain:
    region: _Region
    left_forms: tuple[ReadForm, ...]
    right_forms: tuple[ReadForm, ...]


@dataclass(frozen=True)
class _StationChart:
    points: tuple[Vector, ...]
    bounds: tuple[LinearBound, ...]
    forms: tuple[ReadForm, ...]

    @property
    def dimension(self) -> int:
        return len(self.points[0])


def _cross(origin: Vector, a: Vector, b: Vector) -> Fraction:
    return (a[0] - origin[0]) * (b[1] - origin[1]) - (a[1] - origin[1]) * (b[0] - origin[0])


def _polygon(points: tuple[Vector, ...]) -> tuple[Vector, ...]:
    ordered = sorted(set(points))

    def chain(sequence):
        result = []
        for point in sequence:
            while len(result) >= 2 and _cross(result[-2], result[-1], point) <= 0:
                result.pop()
            result.append(point)
        return result

    return tuple(chain(ordered)[:-1] + chain(reversed(ordered))[:-1])


def _station_chart(evidence: StationEvidence) -> _StationChart:
    origin = evidence.vertices[0]
    axes, directions = affine_frame(evidence.vertices)
    if not axes:
        return _StationChart(((),), (), tuple(ReadForm(value, ()) for value in origin))

    projected = tuple(tuple(vertex[axis] - origin[axis] for axis in axes) for vertex in evidence.vertices)
    first = directions[0]
    axis = axes[0]
    if len(axes) == 1:
        left, right = min(projected), max(projected)
        forms = tuple(ReadForm(value, (delta / first[axis],)) for value, delta in zip(origin, first))
        bounds = (LinearBound((Fraction(-1),), -left[0]), LinearBound((Fraction(1),), right[0]))
        return _StationChart((left, right), bounds, forms)

    second = directions[1]
    other = axes[1]
    determinant = first[axis] * second[other] - first[other] * second[axis]
    forms = tuple(ReadForm(value, (
        (u * second[other] - v * first[other]) / determinant,
        (v * first[axis] - u * second[axis]) / determinant,
    )) for value, u, v in zip(origin, first, second))

    polygon = _polygon(projected)
    bounds = []
    for start, end in zip(polygon, polygon[1:] + polygon[:1]):
        dx, dy = end[0] - start[0], end[1] - start[1]
        bounds.append(LinearBound((dy, -dx), dy * start[0] - dx * start[1]))
    return _StationChart(polygon, tuple(bounds), forms)


def build_product_domain(left: StationEvidence, right: StationEvidence) -> ProductDomain:
    left_chart = _station_chart(left)
    right_chart = _station_chart(right)
    before = (Fraction(0),) * left_chart.dimension
    after = (Fraction(0),) * right_chart.dimension
    bounds = tuple(LinearBound(bound.coefficients + after, bound.limit) for bound in left_chart.bounds)
    bounds += tuple(LinearBound(before + bound.coefficients, bound.limit) for bound in right_chart.bounds)
    vertices = []
    for left_point, right_point in product(left_chart.points, right_chart.points):
        point = left_point + right_point
        faces = sum(1 << index for index, bound in enumerate(bounds) if bound.residual(point) == 0)
        vertices.append(_Vertex(point, faces))
    left_forms = tuple(ReadForm(form.constant, form.coefficients + after) for form in left_chart.forms)
    right_forms = tuple(ReadForm(form.constant, before + form.coefficients) for form in right_chart.forms)
    return ProductDomain(_Region(tuple(vertices), len(bounds)), left_forms, right_forms)


def is_region_feasible(domain: ProductDomain, bounds=()) -> bool:
    return domain.region.restrict(tuple(bounds)) is not None
