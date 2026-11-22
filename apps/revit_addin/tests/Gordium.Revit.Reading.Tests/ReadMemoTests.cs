using Xunit;

namespace Gordium.Revit.Reading.Tests;

/// <summary>The read's memo (<see cref="ReadMemo{TKey, TValue}"/>): with a scope open each key is worked out once and the
/// same value handed back after; with none open, worked out every time, as before; a throw is never kept; the scope's
/// end lets every value go and tells its hits and misses.</summary>
public sealed class ReadMemoTests
{
    [Fact]
    public void With_no_scope_open_every_ask_works_the_value_out_afresh()
    {
        var memo = new ReadMemo<int, object>();
        var made = 0;
        var a = memo.Get(1, () => { made++; return new object(); });
        var b = memo.Get(1, () => { made++; return new object(); });
        Assert.NotSame(a, b);
        Assert.Equal(2, made);
        Assert.False(memo.IsOpen);
    }

    [Fact]
    public void With_a_scope_open_each_key_is_worked_out_once_and_its_hits_and_misses_told_at_its_end()
    {
        var memo = new ReadMemo<int, object>();
        var made = new List<int>();
        (long Hits, long Misses)? told = null;
        object first;
        using (memo.Open((h, m) => told = (h, m)))
        {
            Assert.True(memo.IsOpen);
            first = memo.Get(7, () => { made.Add(7); return new object(); });
            Assert.Same(first, memo.Get(7, () => { made.Add(7); return new object(); }));
            Assert.Same(first, memo.Get(7, () => throw new InvalidOperationException("never asked again")));
            var other = memo.Get(8, () => { made.Add(8); return new object(); });
            Assert.NotSame(first, other);
            Assert.Null(told);                                // told only when the scope ends
        }
        Assert.Equal([7, 8], made);
        Assert.Equal((2L, 2L), told);
        // the scope's end lets every value go
        Assert.False(memo.IsOpen);
        Assert.NotSame(first, memo.Get(7, () => new object()));
    }

    [Fact]
    public void A_value_that_throws_is_never_kept_and_throws_again_worked_out_afresh()
    {
        var memo = new ReadMemo<string, int>();
        var tries = 0;
        using (memo.Open())
        {
            Assert.Throws<InvalidOperationException>(() => memo.Get("a", () => { tries++; throw new InvalidOperationException(); }));
            Assert.Throws<InvalidOperationException>(() => memo.Get("a", () => { tries++; throw new InvalidOperationException(); }));
            Assert.Equal(3, memo.Get("a", () => { tries++; return 3; }));
            Assert.Equal(3, memo.Get("a", () => { tries++; return 4; }));
        }
        Assert.Equal(3, tries);
    }

    [Fact]
    public void A_scope_opened_inside_another_keeps_its_own_values_and_the_outer_ones_come_back()
    {
        var memo = new ReadMemo<int, string>();
        var told = new List<(long, long)>();
        using (memo.Open((h, m) => told.Add((h, m))))
        {
            Assert.Equal("outer", memo.Get(1, () => "outer"));
            using (memo.Open((h, m) => told.Add((h, m))))
                Assert.Equal("inner", memo.Get(1, () => "inner"));
            Assert.Equal("outer", memo.Get(1, () => "again"));
            var close = memo.Open();
            close.Dispose();
            close.Dispose();                                  // twice: no harm, the outer scope still open
            Assert.True(memo.IsOpen);
            Assert.Equal("outer", memo.Get(1, () => "again"));
        }
        Assert.False(memo.IsOpen);
        Assert.Equal([(0L, 1L), (2L, 1L)], told);            // the inner scope's, then the outer's
    }
}
