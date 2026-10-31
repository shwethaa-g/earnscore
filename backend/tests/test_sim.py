import numpy as np

from app.sim.life import live, make_persona


def test_generated_statements_have_no_zero_amount_lines():
    # this persona has weeks where nothing is left for discretionary spending
    p = make_persona(np.random.default_rng(4242), 4242, "Kumar Velu", "Chennai", "rider", 60, 1)
    life = live(p, seed=4242)
    assert life.txns
    assert all(t.amount > 0 for t in life.txns)
    assert all(r.amount > 0 for r in life.payouts)
