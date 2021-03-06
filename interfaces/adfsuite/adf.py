import numpy as np

from subprocess import CalledProcessError

from .scmjob import SCMJob, SCMResults
from ...core.errors import ResultsError
from ...core.settings import Settings
from ...core.functions import config, log
from ...tools.units import Units
from ...tools.periodic_table import PT


__all__ = ['ADFJob', 'ADFResults']


class ADFResults(SCMResults):
    """A specialized |SCMResults| subclass for accessing the results of |ADFJob|."""
    _kfext = '.t21'
    _rename_map = {'TAPE{}'.format(i) : '$JN.t{}'.format(i) for i in range(10,100)}


    def get_properties(self):
        """get_properties()
        Return a dictionary with all the entries from ``Properties`` section in the main KF file (``$JN.t21``).
        """
        ret = {}
        for sec,var in self._kf:
            if sec == 'Properties':
                ret[var] = self.readkf(sec,var)
        return ret


    def get_main_molecule(self):
        """get_main_molecule()
        Return a |Molecule| instance based on the ``Geometry`` section in the main KF file (``$JN.t21``).

        For runs with multiple geometries (geometry optimization, transition state search, intrinsic reaction coordinate) this is the **final** geometry. In such a case, to access the initial (or any intermediate) coordinates please use :meth:`get_input_molecule` or extract coordinates from section ``History``, variables ``xyz 1``, ``xyz 2`` and so on. Mind the fact that all coordinates written by ADF to ``History`` section are in bohr and internal atom order::

            mol = results.get_molecule(section='History', variable='xyz 1', unit='bohr', internal=True)
        """
        return self.get_molecule(section='Geometry', variable='xyz InputOrder', unit='bohr')


    def get_input_molecule(self):
        """get_input_molecule()
        Return a |Molecule| instance with initial coordinates.

        All data used by this method is taken from ``$JN.t21`` file. The ``molecule`` attribute of the corresponding job is ignored.
        """
        if ('History', 'nr of geometries') in self._kf:
            return self.get_molecule(section='History', variable='xyz 1', unit='bohr', internal=True)
        return self.get_main_molecule()


    def get_energy(self, unit='au'):
        """get_energy(unit='au')
        Return final bond energy, expressed in *unit*.
        """
        return self._get_single_value('Energy', 'Bond Energy', unit)


    def get_dipole_vector(self, unit='au'):
        """get_dipole_vector(unit='au')
        Return the dipole vector, expressed in *unit*.
        """
        prop = self.get_properties()
        if 'Dipole' in prop:
            return Units.convert(prop['Dipole'], 'au', unit)
        raise ResultsError("'Dipole' not present in 'Properties' section of {}".format(self._kfpath()))


    def get_gradients(self, eUnit='au', lUnit='bohr'):
        """get_gradients(eUnit='au', lUnit='bohr')
        Returns the cartesian gradients from the 'Gradients_InputOrder' field of the 'GeoOpt' Section in the kf-file, expressed in given units. Returned value is a numpy array with shape (nAtoms,3).
        """
        gradients = np.array(self.readkf('GeoOpt','Gradients_InputOrder'))
        gradients.shape = (-1,3)
        gradients *= (Units.conversion_ratio('au',eUnit) / Units.conversion_ratio('bohr',lUnit))
        return gradients


    def get_energy_decomposition(self, unit='au'):
        """get_energy(unit='au')
        Return a dictionary with energy decomposition terms, expressed in *unit*.

        The following keys are present in the returned dictionary: ``Electrostatic``, ``Kinetic``, ``Coulomb``, ``XC``. The sum of all the values is equal to the value returned by :meth:`get_energy`.
        """
        ret = {}
        ret['Electrostatic'] = self._get_single_value('Energy', 'Electrostatic Energy', unit)
        ret['Kinetic'] = self._get_single_value('Energy', 'Kinetic Energy', unit)
        ret['Coulomb'] = self._get_single_value('Energy', 'Elstat Interaction', unit)
        ret['XC'] = self._get_single_value('Energy', 'XC Energy', unit)
        return ret


    def get_timings(self):
        """get_timings()

        Return a dictionary with timing statistics of the job execution. Returned dictionary contains keys ``cpu``, ``system`` and ``elapsed``. The values are corresponding timings, expressed in seconds.
        """
        last = self.grep_output(' Total Used : ')[-1].split()
        ret = {}
        ret['elapsed'] = float(last[-1])
        ret['system'] = float(last[-3])
        ret['cpu'] = float(last[-5])
        return ret


    def _atomic_numbers_input_order(self):
        """_atomic_numbers_input_order()
        Return a list of atomic numbers, in the input order.
        """
        n = self.readkf('Geometry', 'nr of atoms')
        tmp = self.readkf('Geometry', 'atomtype').split()
        atomtypes = {i+1 : PT.get_atomic_number(tmp[i]) for i in range(len(tmp))}
        atomtype_idx = self.readkf('Geometry', 'fragment and atomtype index')[-n:]
        atnums = [atomtypes[i] for i in atomtype_idx]
        return self.to_input_order(atnums)


    def _int2inp(self):
        """_int2inp()
        Get mapping from the internal atom order to the input atom order.
        """
        aoi = self.readkf('Geometry', 'atom order index')
        n = len(aoi)//2
        return aoi[:n]


    def recreate_molecule(self):
        """Recreate the input molecule for the corresponding job based on files present in the job folder. This method is used by |load_external|.
        """
        if self._kfpresent():
            return self.get_input_molecule()
        return None


    def recreate_settings(self):
        """Recreate the input |Settings| instance for the corresponding job based on files present in the job folder. This method is used by |load_external|.
        """
        if self._kfpresent():
            if ('General', 'Input') in self._kf:
                tmp = self.readkf('General', 'Input')
                user_input = '\n'.join([tmp[i:160+i].rstrip() for i in range(0,len(tmp),160)])
            else:
                user_input = self.readkf('General', 'user input')
            try:
                from scm.input_parser import input_to_settings
                inp = input_to_settings(user_input, program='adf', silent=True)
            except CalledProcessError:
                from scm.input_parser import convert_legacy_input
                new_input = convert_legacy_input(user_input, program='adf')
                try:
                    inp = input_to_settings(new_input, program='adf', silent=True)
                except:
                    log('Failed to recreate input settings from {}'.format(self._kf.path, 5))
                    return None
            except:
                log('Failed to recreate input settings from {}'.format(self._kf.path, 5))
                return None

            s = Settings()
            s.input = inp
            del s.input[s.input.find_case('atoms')]
            s.soft_update(config.job)
            return s
        return None


class ADFJob(SCMJob):
    _result_type = ADFResults
    _command = 'adf'

    def _serialize_mol(self):
        for i,atom in enumerate(self.molecule):
            smb = self._atom_symbol(atom)
            suffix = ''
            if 'adf' in atom.properties and 'fragment' in atom.properties.adf:
                suffix += 'f={fragment} '
            if 'adf' in atom.properties and 'block' in atom.properties.adf:
                suffix += 'b={block}'

            self.settings.input.atoms['_'+str(i+1)] = ('{:>5}'.format(i+1)) + atom.str(symbol=smb, suffix=suffix, suffix_dict=atom.properties.adf)

    def _remove_mol(self):
        if 'atoms' in self.settings.input:
            del self.settings.input.atoms
