from pathlib import Path

from general_utilities.import_utils.module_loader.module_loader import ModuleLoader
from mrcepid_test_loader import test_loader_ingester
from mrcepid_test_loader.test_loader_association_pack import TestLoaderProgramArgs, TestLoaderAssociationPack


class LoadModule(ModuleLoader):

    def __init__(self, output_prefix: str, input_args: str):

        super().__init__(output_prefix, input_args)

    def start_module(self) -> None:

        start_test = Path(f'{self.output_prefix}.start_worked.txt')
        with start_test.open('w') as worked_file:
            worked_file.write('module start worked')

        # Retrieve outputs – all tools _should_ append to the outputs object so they can be retrieved here.
        self.set_outputs([start_test])

    def _load_module_options(self) -> None:
        pass

    def _parse_options(self) -> TestLoaderProgramArgs:
        return TestLoaderProgramArgs(**vars(self._parser.parse_args(self._split_options(self._input_args))))

    def _ingest_data(self, parsed_options: TestLoaderProgramArgs) -> TestLoaderAssociationPack:
        ingested_data = test_loader_ingester.IngestData(parsed_options)
        return ingested_data.get_association_pack()
