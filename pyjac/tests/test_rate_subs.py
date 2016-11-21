#compatibility
from builtins import range

#system
import os
import filecmp

#local imports
from ..core.rate_subs import rate_const_kernel_gen, get_rate_eqn, assign_rates
from ..core.loopy_utils import auto_run, loopy_options, RateSpecialization
from ..utils import create_dir
from . import TestClass
from ..core.reaction_types import reaction_type

#modules
from optionloop import OptionLoop
import cantera as ct
import numpy as np
from nose.plugins.attrib import attr

class SubTest(TestClass):
    def __populate(self):
        T = self.store.T
        ref_const = self.store.fwd_rate_constants
        return T, ref_const, ref_const.T.copy()

    def test_get_rate_eqs(self):
        eqs = {'conp' : self.store.conp_eqs,
                'conv' : self.store.conv_eqs}
        pre, eq = get_rate_eqn(eqs)

        #first check they are equal
        assert 'exp(' + str(pre) + ')' == eq

        #second check the form
        assert eq == 'exp(-T_inv*Ta[i] + beta[i]*logT + logA[i])'

    def test_assign_rates(self):
        reacs = self.store.reacs
        result = assign_rates(reacs, RateSpecialization.full)

        #test rate type
        assert np.all(result['simple']['type'] == 0)

        #import gas in cantera for testing
        gas = ct.Solution('test.cti')

        def __tester(result):
            #test return value
            assert 'simple' in result and 'cheb' in result and 'plog' in result

            #test num, mask, and offset
            plog_inds, plog_reacs = zip(*[(i, x) for i, x in enumerate(gas.reactions())
                    if isinstance(x, ct.PlogReaction)])
            assert result['plog']['num'] = len(plog_inds)
            assert result['plog']['mask'] = np.array(np.sorted(plog_inds, dtype=np.int32))
            if np.all(np.diff(result['plog']['mask']) == 1):
                assert result['plog']['offset'] == result['plog']['mask'][0]
            else:
                assert result['plog']['offset'] is None

            cheb_inds, cheb_reacs = zip(*[(i, x) for i, x in enumerate(gas.reactions())
                    if isinstance(x, ct.ChebyshevReaction)])
            assert result['cheb']['num'] = len(cheb_inds)
            assert result['cheb']['mask'] = np.array(np.sorted(cheb_inds, dtype=np.int32))
            if np.all(np.diff(result['cheb']['mask']) == 1):
                assert result['cheb']['offset'] == result['cheb']['mask'][0]
            else:
                assert result['cheb']['offset'] is None

            elem_inds = sort(list(set(plog_inds).union(set(cheb_inds))))
            assert result['simple']['num'] = len(cheb_inds)
            assert result['simple']['mask'] = np.array(np.sorted(cheb_inds, dtype=np.int32))
            if np.all(np.diff(result['simple']['mask']) == 1):
                assert result['simple']['offset'] == result['simple']['mask'][0]
            else:
                assert result['simple']['offset'] is None

        __tester()

        result = assign_rates(reacs, RateSpecialization.hybrid)

        #test rate type
        rtypes = []
        for reac in gas.reactions():
            if not (isinstance(reac, ct.PlogReaction) or isinstance(reac, ct.ChebyshevReaction)):
                Ea = reac.rate.activation_energy
                b = reac.rate.temperature_exponent
                if Ea == 0 and b == 0:
                    rtypes[i].append(0)
                elif Ea == 0 and int(b) == b:
                    rtypes.append(1)
                else:
                    rtypes.append(2)
        assert result['simple']['type'] == np.array(rtypes)
        __tester()

        result = assign_rates(reacs, RateSpecialization.full)

        #test rate type
        rtypes = []
        for reac in gas.reactions():
            if not (isinstance(reac, ct.PlogReaction) or isinstance(reac, ct.ChebyshevReaction)):
                Ea = reac.rate.activation_energy
                b = reac.rate.temperature_exponent
                if Ea == 0 and b == 0:
                    rtypes[i].append(0)
                elif Ea == 0 and int(b) == b:
                    rtypes.append(1)
                elif Ea == 0:
                    rtypes.append(2)
                elif b == 0:
                    rtypes.append(3)
                else:
                    rtypes.append(4)
        assert result['simple']['type'] == np.array(rtypes)
        __tester()


    @attr('long')
    def test_rate_constants(self):
        T = self.store.T
        ref_const = self.store.fwd_rate_constants
        ref_const_T = ref_const.T.copy()

        eqs = {'conp' : self.store.conp_eqs,
                'conv' : self.store.conv_eqs}
        pre, eq = get_rate_eqn(eqs)

        oploop = OptionLoop({'lang': ['opencl'],
            'width' : [4, None],
            'depth' : [4, None],
            'ilp' : [True, False],
            'unr' : [None, 4],
            'order' : ['C', 'F'],
            'device' : ['0:0', '1'],
            'ratespec' : [x for x in RateSpecialization],
            'ratespec_kernels' : [True, False]
            })

        reacs = self.store.reacs
        compare_mask = [i for i, x in enumerate(reacs) if x.match((reaction_type.elementary,))]

        for state in oploop:
            try:
                opt = loopy_options(**{x : state[x] for x in
                    state if x != 'device'})
                knl = rate_const_kernel_gen(eq, pre, reacs, opt,
                    test_size=self.store.test_size)

                ref = ref_const#ref_const if state['order'] == 'gpu' else ref_const_T
                assert auto_run(knl, ref, device=state['device'],
                    T_arr=T, compare_mask=compare_mask)
            except Exception as e:
                if not(state['width'] and state['depth']):
                    raise e