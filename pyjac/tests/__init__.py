#compatibility fixes
from builtins import range

#modules
import cantera as ct
import numpy as np
import unittest
import loopy as lp

#system
import os

#local imports
from ..sympy.sympy_interpreter import load_equations
from ..core.mech_interpret import read_mech_ct

test_size = 10000

class storage(object):
    def __init__(self, conp_vars, conp_eqs, conv_vars,
        conv_eqs, gas, specs, reacs):
        self.conp_vars = conp_vars
        self.conp_eqs = conp_eqs
        self.conv_vars = conv_vars
        self.conv_eqs = conv_eqs
        self.gas = gas
        self.specs = specs
        self.reacs = reacs
        self.test_size = test_size

        #create states
        self.T = np.random.uniform(600, 2200, size=test_size)
        self.P = np.random.uniform(0.5, 50, size=test_size) * ct.one_atm
        self.Y = np.random.uniform(0, 1, size=(self.gas.n_species, test_size))
        self.concs = np.empty_like(self.Y)
        self.fwd_rate_constants = np.zeros((self.gas.n_reactions, test_size))

        #third body indicies
        self.thd_inds = np.array([i for i, x in enumerate(gas.reactions())
            if isinstance(x, ct.FalloffReaction) or
                isinstance(x, ct.ChemicallyActivatedReaction) or
                isinstance(x, ct.ThreeBodyReaction)])
        self.ref_thd = np.zeros((self.thd_inds.size, test_size))
        thd_eff_maps = []
        for i in self.thd_inds:
            default = gas.reaction(i).default_efficiency
            #fill all missing with default
            thd_eff_map = [default if j not in gas.reaction(i).efficiencies
                              else gas.reaction(i).efficiencies[j] for j in gas.species_names]
            thd_eff_maps.append(np.array(thd_eff_map))
        thd_eff_maps = np.array(thd_eff_maps)

        #various indicies and mappings
        self.rev_inds = np.array([i for i in range(gas.n_reactions) if gas.is_reversible(i)])
        self.rev_rate_constants = np.zeros((self.rev_inds.size, test_size))
        self.equilibrium_constants = np.zeros((self.rev_inds.size, test_size))

        self.fall_inds = np.array([i for i, x in enumerate(gas.reactions())
            if isinstance(x, ct.FalloffReaction)])
        self.sri_inds = np.array([i for i, x in enumerate(gas.reactions())
            if i in self.fall_inds and isinstance(x.falloff, ct.SriFalloff)])
        self.troe_inds = np.array([i for i, x in enumerate(gas.reactions())
            if i in self.fall_inds and isinstance(x.falloff, ct.TroeFalloff)])
        troe_to_pr_map = np.array([np.where(self.fall_inds == j)[0][0] for j in self.troe_inds])
        sri_to_pr_map = np.array([np.where(self.fall_inds == j)[0][0] for j in self.sri_inds])
        self.ref_Pr = np.zeros((self.fall_inds.size, test_size))
        self.ref_Sri = np.zeros((self.sri_inds.size, test_size))
        self.ref_Troe = np.zeros((self.troe_inds.size, test_size))
        self.ref_B_rev = np.zeros((gas.n_species, test_size))
        #and the corresponding reactions
        fall_reacs = [gas.reaction(j) for j in self.fall_inds]
        sri_reacs = [gas.reaction(j) for j in self.sri_inds]
        troe_reacs = [gas.reaction(j) for j in self.troe_inds]

        #convenience method for reduced pressure evaluation
        arrhen_temp = np.zeros(self.fall_inds.size)
        def pr_eval(i, j):
            reac = fall_reacs[j]
            return reac.low_rate(self.T[i]) / reac.high_rate(self.T[i])

        thd_to_fall_map = np.where(np.in1d(self.thd_inds, self.fall_inds))[0]

        for i in range(test_size):
            self.gas.TPY = self.T[i], self.P[i], self.Y[:, i]
            self.concs[:, i] = self.gas.concentrations[:]

            #store various information
            self.fwd_rate_constants[:, i] = gas.forward_rate_constants[:]
            self.rev_rate_constants[:, i] = gas.reverse_rate_constants[self.rev_inds]
            self.equilibrium_constants[:, i] = gas.equilibrium_constants[self.rev_inds]
            self.ref_thd[:, i] = np.dot(thd_eff_maps, self.concs[:, i])
            for j in range(self.fall_inds.size):
                arrhen_temp[j] = pr_eval(i, j)
            self.ref_Pr[:, i] = self.ref_thd[thd_to_fall_map, i] * arrhen_temp
            for j in range(self.sri_inds.size):
                self.ref_Sri[j, i] = sri_reacs[j].falloff(self.T[i], self.ref_Pr[sri_to_pr_map[j], i])
            for j in range(self.troe_inds.size):
                self.ref_Troe[j, i] = troe_reacs[j].falloff(self.T[i], self.ref_Pr[troe_to_pr_map[j], i])
            for j in range(gas.n_species):
                self.ref_B_rev[j, i] = gas.species(j).thermo.s(self.T[i]) / ct.gas_constant -\
                    gas.species(j).thermo.h(self.T[i]) / (ct.gas_constant * self.T[i]) - np.log(self.T[i])


class TestClass(unittest.TestCase):
    #global setup var
    _is_setup = False
    _store = None
    @property
    def store(self):
        return self._store
    @store.setter
    def store(self, val):
        self._store = val
    @property
    def is_setup(self):
        return self._is_setup
    @is_setup.setter
    def is_setup(self, val):
        self._is_setup = val

    def setUp(self):
        lp.set_caching_enabled(False)
        if not self.is_setup:
            #load equations
            conp_vars, conp_eqs = load_equations(True)
            conv_vars, conv_eqs = load_equations(False)
            self.dirpath = os.path.dirname(os.path.realpath(__file__))
            #load the gas
            gas = ct.Solution(os.path.join(self.dirpath, 'test.cti'))
            #the mechanism
            elems, specs, reacs = read_mech_ct(os.path.join(self.dirpath, 'test.cti'))
            self.store = storage(conp_vars, conp_eqs, conv_vars,
                conv_eqs, gas, specs, reacs)
            self.is_setup = True