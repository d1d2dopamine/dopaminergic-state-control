from dsc.stats import benjamini_hochberg, benjamini_hochberg_total, hypergeom_sf


def test_hypergeom_tail_decreases_for_more_observed_successes():
    p3 = hypergeom_sf(2, 1000, 20, 50)
    p8 = hypergeom_sf(7, 1000, 20, 50)
    assert 0 <= p8 < p3 <= 1


def test_bh_is_bounded_and_monotone_by_sorted_p():
    p=[0.001,0.02,0.5,0.04]
    q=benjamini_hochberg(p)
    assert all(0 <= x <= 1 for x in q)
    pairs=sorted(zip(p,q))
    assert all(pairs[i][1] <= pairs[i+1][1] for i in range(len(pairs)-1))


def test_sparse_bh_corrects_against_full_universe():
    q_sparse=benjamini_hochberg([1e-6,1e-4])
    q_full=benjamini_hochberg_total([1e-6,1e-4],1000)
    assert q_full[0] >= q_sparse[0]
    assert q_full[1] >= q_sparse[1]
