from dataclasses import dataclass
from general_utilities.import_utils.module_loader.association_pack import AssociationPack, ProgramArgs


@dataclass
class TestLoaderProgramArgs(ProgramArgs):

    def __post_init__(self):
        """@dataclass automatically calls this method after calling its own __init__().

        This is required in the subclass because dataclasses do not call the __init__ of their super o.0

        """
        self._check_opts()

    def _check_opts(self):
        pass


class TestLoaderAssociationPack(AssociationPack):

    def __init__(self, association_pack: AssociationPack):

        super().__init__(association_pack.is_binary, association_pack.sex, association_pack.threads,
                         association_pack.pheno_names, association_pack.ignore_base_covariates,
                         association_pack.found_quantitative_covariates, association_pack.found_categorical_covariates,
                         association_pack.cmd_executor)
