import unittest
import time
from typed_python import _types
from typed_python import Class, Final, ListOf, Held, Member, Entrypoint, Forward, pointerTo


@Held
class H(Class, Final):
    x = Member(int, nonempty=True)
    y = Member(float, nonempty=True)

    def f(self):
        return self.x + self.y

    def increment(self):
        self.x += 1
        self.y += 1

    @Entrypoint
    def entrypointedIncrement(self):
        self.x += 1
        self.y += 1

    @Entrypoint
    def getX(self):
        return self.x

    @Entrypoint
    def pointerToSelf(self):
        return pointerTo(self)

    def __repr__(self):
        return "ReprForH"

    def __str__(self):
        return "StrForH"


Complex = Forward("Complex")


@Complex.define
@Held
class Complex(Class, Final):
    real = Member(float, nonempty=True)
    imag = Member(float, nonempty=True)

    def __add__(self, other: float):
        return Complex(real=self.real + other, imag=self.imag)

    def __add__(self, other: Complex):  # noqa
        return Complex(real=self.real + other.real, imag=self.imag + other.imag)

    def __mul__(self, other: float):
        return Complex(real=self.real * other, imag=self.imag * other)

    def __mul__(self, other: Complex):  # noqa
        return Complex(
            real=self.real * other.real - self.imag * other.imag,
            imag=self.imag * other.real + self.real * other.imag
        )


class TestHeldClassCompilation(unittest.TestCase):
    def checkCompiler(self, f, *args, **kwargs):
        interpretedOutput = f(*args, **kwargs)

        compiledOutput = Entrypoint(f)(*args, **kwargs)

        self.assertEqual(compiledOutput, interpretedOutput)

    def test_held_class_pointer_to_self(self):
        @Entrypoint
        def callPointerTo(h):
            return pointerTo(h)

        h = H(x=2, y=3)

        assert callPointerTo(h) == pointerTo(h)
        assert h.pointerToSelf() == pointerTo(h)

    def test_held_class_repr(self):
        assert repr(H()) == "ReprForH"
        self.checkCompiler(lambda x: repr(x), H())

    def test_held_class_str(self):
        assert str(H()) == "StrForH"
        self.checkCompiler(lambda x: str(x), H())

    def test_held_class_entrypointed_methods(self):
        h1 = H(x=2, y=3)
        h2 = H(x=2, y=3)

        h1.entrypointedIncrement()
        h2.increment()

        assert h1.x == h2.x
        assert h1.getX() == h1.x

    def test_stringify_held_class(self):
        h = H(x=2, y=3)

        @Entrypoint
        def callStr(h):
            return str(h)

        assert str(h) == callStr(h)

    def test_pointer_to_held_class_compiles(self):
        h = H(x=2, y=3)

        @Entrypoint
        def getPtr(h):
            return pointerTo(h)

        assert pointerTo(h) == getPtr(h)

    def test_pass_held_to_function_with_signature(self):
        @Entrypoint
        def f(h: H):
            h.x = 100

        @Entrypoint
        def g():
            h = H()
            f(h)
            return h

        assert g().x == 100

    def test_pass_held_by_ref_across_entrypoint(self):
        @Entrypoint
        def g(h):
            h.x = 100

        h = H()
        g(h)
        assert h.x == 100

    def test_compile_held_class(self):
        @Held
        class H(Class, Final):
            x = Member(int, nonempty=True)
            y = Member(float, nonempty=True)

            def f(self):
                return self.x + self.y

            def typeOfSelf(self):
                return type(self)

        class C(Class, Final):
            h1 = Member(H)
            h2 = Member(H)

        c = C()

        self.checkCompiler(lambda c: type(c.h1), c)
        self.checkCompiler(lambda c: c.h1.x, c)
        self.checkCompiler(lambda c: c.h1.y, c)
        self.checkCompiler(lambda c: c.h1, c)
        self.checkCompiler(lambda c: type(c.h1.x), c)
        self.checkCompiler(lambda c: c.h1.x, c)

        c.h1.x = 20
        self.checkCompiler(lambda c: c.h1.x, c)

        def move(c):
            c.h2 = c.h1
            return c.h2.x

        self.checkCompiler(move, c)

        self.checkCompiler(lambda c: c.h1.f(), c)
        self.checkCompiler(lambda c: c.h1.typeOfSelf(), c)

    def test_compile_list_of_held_class(self):
        assert not _types._temporaryReferenceTracerActive()

        class H(Class, Final):
            x = Member(int, nonempty=True)
            y = Member(float, nonempty=True)

            def f(self):
                return self.x + self.y

            def increment(self):
                self.x += 1
                self.y += 1

        aList = ListOf(Held(H))()

        @Entrypoint
        def resizeList(l):
            l.resize(10)

        resizeList(aList)

        self.assertEqual(len(aList), 10)
        self.assertEqual(aList[0].x, 0)
        self.assertEqual(aList[0].y, 0.0)

        @Entrypoint
        def getitem(l, x):
            return l[x]

        self.assertEqual(aList[0], getitem(aList, 0))

        def incrementAllRange(l):
            for i in range(len(l)):
                l[i].increment()

        incrementAllRange(aList)

        def testIt(x):
            assert _types._temporaryReferenceTracerActive()
            return x

        testIt(aList[0].increment)

        assert not _types._temporaryReferenceTracerActive()

        self.assertEqual(getitem(aList, 0).x, 1)
        self.assertEqual(getitem(aList, 5).x, 1)

        Entrypoint(incrementAllRange)(aList)

        self.assertEqual(getitem(aList, 0).x, 2)
        self.assertEqual(getitem(aList, 5).x, 2)

        def incrementViaIterator(l):
            for i in l:
                # this is a no-op because 'i' is a copy
                i.increment()

        incrementViaIterator(aList)

        assert not _types._temporaryReferenceTracerActive()

        self.assertEqual(getitem(aList, 0).x, 2)
        self.assertEqual(getitem(aList, 5).x, 2)

        Entrypoint(incrementViaIterator)(aList)

        self.assertEqual(getitem(aList, 0).x, 2)
        self.assertEqual(getitem(aList, 5).x, 2)

    def test_compile_construct_with_init(self):
        @Held
        class H(Class, Final):
            x = Member(int)
            y = Member(float)

            def __init__(self):
                self.x = 0
                self.y = 0

            def __init__(self, x):  # noqa
                self.x = x
                self.y = 0

        self.checkCompiler(lambda: H(x=10).x)

    def test_compile_access_child_held_class(self):
        @Held
        class H2(Class, Final):
            h = Member(H)

        def f():
            h = H2()
            h.h.x = 10
            return h.h.x

        self.checkCompiler(f)

    def test_compile_add_operator(self):
        self.checkCompiler(lambda: (Complex(real=10) + 20).real)
        self.checkCompiler(lambda: (Complex(real=10) + Complex(imag=20)).imag)

    def test_compile_add_operator_perf(self):
        @Entrypoint
        def f(ct):
            x = Complex(real=0, imag=1)
            y = x
            for i in range(ct):
                x = x * y
            return x

        f(100)

        t0 = time.time()
        f(100000000)
        print(time.time() - t0)
