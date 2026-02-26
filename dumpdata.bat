CALL ./venv/Scripts/activate
echo on
:: Environments
python manage.py dumpdata environments.TalosExecutableSwitch environments.TalosExecutableArgument environments.TalosExecutable environments.TalosExecutableArgumentAssignment environments.TalosExecutableSupplementaryFileOrPath environments.ProjectEnvironmentContextKey environments.ProjectEnvironmentStatus environments.ProjectEnvironmentType environments.ProjectEnvironment environments.ContextVariable --output environments/fixtures/initial_data.json --indent 2

:: Frontal Lobe (Reasoning)
python manage.py dumpdata frontal_lobe.ReasoningStatus frontal_lobe.ModelRegistry --output frontal_lobe/fixtures/initial_data.json --indent 2

:: Hydra (Orchestration)
python manage.py dumpdata hydra.HydraTag hydra.HydraSpawnStatus hydra.HydraHeadStatus hydra.HydraDistributionMode hydra.HydraSpell hydra.HydraSpellContext hydra.HydraSpellTarget hydra.HydraSpellArgumentAssignment hydra.HydraSpellbook hydra.HydraSpellbookNode hydra.HydraSpellBookNodeContext hydra.HydraWireType hydra.HydraSpellbookConnectionWire --output hydra/fixtures/initial_data.json --indent 2

:: Talos Parietal (Tools)
python manage.py dumpdata talos_parietal.ToolParameterType talos_parietal.ToolUseType talos_parietal.ToolDefinition talos_parietal.ToolParameter talos_parietal.ToolParameterAssignment talos_parietal.ParameterEnum --output talos_parietal/fixtures/initial_data.json --indent 2
