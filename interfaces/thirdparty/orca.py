import numpy as np

from ...core.basejob import SingleJob
from ...core.settings import Settings
from ...core.results import Results
from ...mol.molecule import Molecule
from ...tools.units import Units


class ORCAResults(Results):
    """
    A class for accessing results of Orca jobs.
    """

    def get_main_molecule(self):
        """ Return a |Molecule| instance with final coordinates read from the .xyz file. """
        return Molecule(filename=self['$JN.xyz'])

    def get_energy(self, unit='au'):
        """ Return the total energy, expressed in *unit*. """
        string = self.grep_output(pattern='FINAL SINGLE POINT ENERGY')
        energy = float(string.split()[4])
        return Units.convert(energy, 'au', unit)

    def get_frequencies(self, unit='cm^-1'):
        """ Return a numpy array of vibrational frequencies, expressed in *unit*. """
        options = '-A ' + str(2 + 3 * len(self.job.molecule.atoms))
        string = self.grep_output(pattern='VIBRATIONAL FREQUENCIES', options=options)
        freq_list = string.spltlines()[3:]
        freqs = np.array([float(freq.split()[1]) for freq in freq_list])
        return freqs * Units.conversion_ratio('cm^-1', unit)


#===========================================================================
#===========================================================================
#===========================================================================


class ORCAJob(SingleJob):
    """
    A class representing a single computational job with ORCA
    `Orca <https://orcaforum.cec.mpg.de>`
    todo:
       * print molecule in internal coordinates
       * print xyz including different basis set
    """
    _result_type = ORCAResults

    def get_input(self):
        """
        Transform all contents of ``input`` branch of  ``settings``
        into string with blocks, subblocks, keys and values. The branch
        self.settings.input.main corresponds to the lines starting with
        the special character ! in the Orca input.

        Orca *end* keyword is mandatory for only a subset of sections,
        For instance the following orca input shows the keywords *methods*
        and *basis* use of end.

            ! UKS B3LYP/G SV(P) SV/J TightSCF Direct Grid3 FinalGrid4

            %method SpecialGridAtoms 26
                    SpecialGridIntAcc 7
                    end
            %basis NewGTO 26 "CP(PPP)" end
                   NewAuxGTO 26 "TZV/J" end
                   end

        In order to specify when the *end* keyword must be used,
        the following syntasis can be used.


        job = Orca(molecule=Molecule(<Path/to/molecule>))
        job.settings.input.main = "UKS B3LYP/G SV(P) SV/J TightSCF Direct Grid3 FinalGrid4"
        job.settings.input.method.SpecialGridAtoms = 26
        job.settings.input.method.SpecialGridIntAcc = 7

        job.settings.input.basis.NewGTO._end = "26 \"CP(PPP)\""
        job.settings.input.basis.NewAuxGTO._end = "26 \"TZV/J\""
        """
        def get_end(s):
            if (not isinstance(s, Settings)) or ('_end' not in s):
                return s
            else:
                return '{} end'.format(s['_end'])

        def pretty_print_inner(s, indent):
            inp = ''
            for i, (key, value) in enumerate(s.items()):
                end = get_end(value)
                if i == 0:
                    inp += ' {} {}\n'.format(key, end)
                else:
                    inp += '{}{} {}\n'.format(indent, key, end)
            return inp

        def pretty_print_orca(s, indent=''):
            inp = ''
            if isinstance(s, Settings):
                for k, v in s.items():
                    if k == 'main':
                        inp += '! {}\n\n'.format(pretty_print_orca(v, indent))
                    else:
                        indent2 = (len(k) + 2) * ' '
                        if not isinstance(v, Settings):
                            block = pretty_print_orca(v)
                        else:
                            block = pretty_print_inner(v, indent2)
                        inp += '%{}{}{}end\n\n'.format(k, block, indent2)
            elif isinstance(s, list):
                for elem in s:
                    inp += '{}'.format(elem)
            else:
                inp += '{}'.format(s)
            return inp

        inp = pretty_print_orca(self.settings.input)
        inp_mol = self.print_molecule()

        return inp + inp_mol

    def print_molecule(self):
        """
        pretty print a molecule in the Orca format.
        """
        mol = self.molecule
        if mol:
            if 'charge' in mol.properties and isinstance(mol.properties.charge, int):
                charge = mol.properties.charge
            else:
                charge = 0
            if 'multiplicity' in mol.properties and isinstance(mol.properties.multiplicity, int):
                multi = mol.properties.multiplicity
            else:
                multi = 1
            xyz = '\n'.join(at.str(symbol=True, space=11, decimal=5) for at in mol.atoms)
            return '* xyz {} {}\n{}\n*\n\n'.format(charge, multi, xyz)
        else:
            return ''

    def get_runscript(self):
        """
        Running orca is straightforward, simply:
        */absolute/path/to/orca myinput.inp*
        """
        return 'orca {}'.format(self._filename('inp'))

    def check(self):
        """
        Look for the normal termination signal in Orca output
        """
        s = self.results.grep_output("ORCA TERMINATED NORMALLY")
        return len(s) > 0
