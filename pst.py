# Changes
import yaml
import pyemu
import tempfile
from dpestool.functions import *

def pst(
        cultivar_parameters=None,
        ecotype_parameters=None,
        dataframe_observations=None,
        output_path=None,
        model_comand_line=None,
        noptmax=1000,
        pst_filename='PEST_CONTROL.pst',
        input_output_file_pairs=None
):
    """
    Create and update a PEST control file (PST) for CERES wheat model calibration.

    Args:
                            bounds, and groupings. It should include:
        cultivar_parameters (dict): Dictionary containing model parameters with their values,
                            - 'cultivar_parameters': Current parameter values for the specified cultivar.
                            - 'minima_parameters': Minima values for all parameters.
                            - 'maxima_parameters': Maxima values for all parameters.
                            - 'parameters_grouped': Grouping of parameters.
        dataframe_observations (pd.DataFrame or list): DataFrame or list of DataFrames containing observations to include in the PST file.
            Each DataFrame must include columns: 'variable_name', 'value_measured', and 'group'
        output_path (str): Directory to save the PST file. Defaults to the current working directory if not provided.
        model_comand_line (str): Command line for running the model executable.
        noptmax (int): Maximum number of iterations for the optimization process. Default is 1000.
        pst_filename (str): The name of the PST file to create or update. Default is 'pest_control_ceres_wheat.pst'.
        input_output_file_pairs (list): List of tuples where each tuple contains an input and output file pair.

    Returns:
        None: This function creates the PST file at the specified `output_path` with the provided name
              (`pst_filename`). It performs validation on inputs, processes observation data,
              sets up parameters, and writes the resulting PST file.


    Raises:
    ValueError: If required arguments are missing or invalid values are encountered.
    FileNotFoundError: If the specified CUL file does not exist.
    Exception: For any other unexpected errors.
    """
    # Define default variables
    yml_pst_file_block = 'PST_FILE'
    yml_file_observation_groups = 'OBSERVATION_GROUPS_SPECIFICATIONS'

    try:
        ## Get the yaml_data
        # Get the directory of the current script
        current_dir = os.path.dirname(os.path.abspath(__file__))
        # Construct the path to arguments.yml
        arguments_file = os.path.join(current_dir, 'arguments.yml')
        # Ensure the YAML file exists
        if not os.path.isfile(arguments_file):
            raise FileNotFoundError(f"YAML file not found: {arguments_file}")
        # Load YAML configuration
        with open(arguments_file, 'r') as yml_file:
            yaml_data = yaml.safe_load(yml_file)

        # Validate inputs
        if not (cultivar_parameters or ecotype_parameters):
            raise ValueError(
                "At least one of `cultivar_parameters` or `ecotype_parameters` must be provided and non-empty.")

        if cultivar_parameters and not isinstance(cultivar_parameters, dict):
            raise ValueError("`cultivar_parameters`, if provided, must be a dictionary.")

        if ecotype_parameters and not isinstance(ecotype_parameters, dict):
            raise ValueError("`ecotype_parameters`, if provided, must be a dictionary.")

        # Additional validation for file extensions based on parameters
        if cultivar_parameters:
            if not any(pair[1].lower().endswith('.cul') for pair in input_output_file_pairs):
                raise ValueError(
                    "If `cultivar_parameters` is provided, at least one file in `input_output_file_pairs` must have a '.CUL' extension.")
        if ecotype_parameters:
            if not any(pair[1].lower().endswith('.eco') for pair in input_output_file_pairs):
                raise ValueError(
                    "If `ecotype_parameters` is provided, at least one file in `input_output_file_pairs` must have a '.ECO' extension.")

        # Validate that at least one file has a '.OUT' extension
        if not any(pair[1].lower().endswith('.out') for pair in input_output_file_pairs):
            raise ValueError("At least one file in `input_output_file_pairs` must have a '.OUT' extension.")

        if dataframe_observations is None:
            raise ValueError("`dataframe_observations` must be provided.")

        # Convert single dataframe to list for consistent processing
        if isinstance(dataframe_observations, pd.DataFrame):
            dataframe_observations = [dataframe_observations]

        if not isinstance(dataframe_observations, list) or not all(
                isinstance(df, pd.DataFrame) for df in dataframe_observations):
            raise ValueError("`dataframe_observations` must be a DataFrame or a list of DataFrames.")

        required_columns = {'variable_name', 'value_measured', 'group'}
        for df in dataframe_observations:
            if not required_columns.issubset(df.columns):
                raise ValueError(
                    "Each DataFrame in `dataframe_observations` must contain 'variable_name', 'value_measured', and 'group' columns.")

        # Get Parameter Group Variables
        observation_groups = yaml_data[yml_pst_file_block][yml_file_observation_groups]

        # Merge dictionaries if both are provided, or use the one that exists
        parameters = {
            'parameters': {**(cultivar_parameters.get('parameters', {}) if cultivar_parameters else {}),
                           **(ecotype_parameters.get('parameters', {}) if ecotype_parameters else {})},
            'minima_parameters': {**(cultivar_parameters.get('minima_parameters', {}) if cultivar_parameters else {}),
                                  **(ecotype_parameters.get('minima_parameters', {}) if ecotype_parameters else {})},
            'maxima_parameters': {**(cultivar_parameters.get('maxima_parameters', {}) if cultivar_parameters else {}),
                                  **(ecotype_parameters.get('maxima_parameters', {}) if ecotype_parameters else {})},
            'parameters_grouped': {**(cultivar_parameters.get('parameters_grouped', {}) if cultivar_parameters else {}),
                                   **(ecotype_parameters.get('parameters_grouped', {}) if ecotype_parameters else {})}
        }

        # Extract cultivar_parameters
        all_params = [
            param for group in parameters['parameters_grouped'].values()
            for param in group.replace(' ', '').split(',')
        ]

        # Create a minimal PST object
        pst = pyemu.pst_utils.generic_pst(all_params)

        # Populate parameters
        for param in all_params:
            pst.parameter_data.loc[param, 'parval1'] = float(parameters['parameters'][param])
            pst.parameter_data.loc[param, "parlbnd"] = float(parameters['minima_parameters'][param])
            pst.parameter_data.loc[param, "parubnd"] = float(parameters['maxima_parameters'][param])
            pst.parameter_data.loc[param, "pargp"] = next(
                (group for group, params in parameters['parameters_grouped'].items() if param in params.split(', ')),
                None)

            # Add PARTRANS and PARCHGLIM
            pst.parameter_data.loc[param, "partrans"] = "none"  # Set PARTRANS to none
            pst.parameter_data.loc[param, "parchglim"] = "relative"  # Set PARCHGLIM to relative

        # Create parameter groups using values from observation_groups
        pargp_data = []
        for group in parameters['parameters_grouped'].keys():
            pargp_entry = {"pargpnme": group}  # Start with the group name
            pargp_entry.update(observation_groups)  # Update with values from observation_groups
            pargp_data.append(pargp_entry)

        # Convert parameter groups list to DataFrame
        pst.parameter_groups = pd.DataFrame(pargp_data)

        # Clear existing observation data
        pst.observation_data = pst.observation_data.iloc[0:0]

        # Process all dataframes
        for df in dataframe_observations:
            # Validate and clean observation data
            df['value_measured'] = pd.to_numeric(df['value_measured'], errors='coerce')
            df = df.dropna(subset=['value_measured'])

            for index, row in df.iterrows():
                obsnme = row['variable_name']
                obsval = row['value_measured']
                obgnme = row['group']
                pst.observation_data.loc[obsnme, 'obsnme'] = obsnme
                pst.observation_data.loc[obsnme, 'obsval'] = obsval
                pst.observation_data.loc[obsnme, 'obgnme'] = obgnme
                pst.observation_data.loc[obsnme, 'weight'] = 1.0  # Default weight

        # ~~~~~~~~ Handle input and output files

        if input_output_file_pairs:
            # Validate file pairs
            if not all(len(pair) == 2 for pair in input_output_file_pairs):
                raise ValueError("Each input_output_file_pair must contain exactly two elements")
            if not all(pair[0].lower().endswith(('.tpl', '.ins')) for pair in input_output_file_pairs):
                raise ValueError("The first element of each pair must be a .tpl or .ins file")

            # Validate file existence
            for pair in input_output_file_pairs:
                validate_file_path(pair[0])  # Validate PEST file (TPL or INS)
                validate_file_path(pair[1])  # Validate model file

            # Function to count TPL and INS files
            def count_file_types(file_pairs):
                tpl_count = sum(1 for pair in file_pairs if pair[0].lower().endswith('.tpl'))
                ins_count = sum(1 for pair in file_pairs if pair[0].lower().endswith('.ins'))
                return tpl_count, ins_count

            # Add quotes to escape spaces
            def escape_spaces(file_pairs):
                return [
                    (f'"{pair[0]}"' if ' ' in pair[0] else pair[0],
                     f'"{pair[1]}"' if ' ' in pair[1] else pair[1])
                    for pair in file_pairs
                ]

            # Escape spaces in paths
            input_output_file_pairs = escape_spaces(input_output_file_pairs)

            # Count TPL and INS files
            tpl_count, ins_count = count_file_types(input_output_file_pairs)

            # Set input files (TPL files)
            pst.model_input_data = pd.DataFrame({
                'pest_file': [pair[0] for pair in input_output_file_pairs if
                              pair[0].strip('"').lower().endswith('.tpl')],
                'model_file': [pair[1] for pair in input_output_file_pairs if
                               pair[0].strip('"').lower().endswith('.tpl')]
            })

            # Set output files (INS files)
            pst.model_output_data = pd.DataFrame({
                'pest_file': [pair[0] for pair in input_output_file_pairs if
                              pair[0].strip('"').lower().endswith('.ins')],
                'model_file': [pair[1] for pair in input_output_file_pairs if
                               pair[0].strip('"').lower().endswith('.ins')]
            })

            # Set NTPLFLE and NINSFLE
            pst.control_data.ntplfle = tpl_count
            pst.control_data.ninsfle = ins_count

        # ~~~~~~~~/ Handle input and output files

        # Set NUMCOM, JACFILE, and MESSFILE
        pst.control_data.numcom = 1
        pst.control_data.jacfile = 0
        pst.control_data.messfile = 0

        # Set LSQR mode
        pst.pestmode = "estimation"

        # ~~~~~~~~ Add LSQR section as a custom attribute

        pst.lsqr_data = {
            "lsqrmode": 1,
            "lsqr_atol": 1e-4,
            "lsqr_btol": 1e-4,
            "lsqr_conlim": 28.0,
            "lsqr_itnlim": 28,
            "lsqrwrite": 0
        }

        # Store the original write method
        original_write = pst.write

        # Define a new write method that replaces SVD with LSQR
        def custom_write(self, filename):
            # First, write to a temporary file
            with tempfile.NamedTemporaryFile(mode='w+', delete=False) as temp_file:
                original_write(temp_file.name)
                temp_filename = temp_file.name

            # Read the content of the temporary file
            with open(temp_filename, 'r') as f:
                content = f.read()

            # Replace SVD section with LSQR
            lsqr_section = f"* lsqr\n  {self.lsqr_data['lsqrmode']}\n  {self.lsqr_data['lsqr_atol']}  {self.lsqr_data['lsqr_btol']}  {self.lsqr_data['lsqr_conlim']}  {self.lsqr_data['lsqr_itnlim']}\n  {self.lsqr_data['lsqrwrite']}\n"
            content = re.sub(r'\* singular value decomposition.*?(?=\*|$)', lsqr_section, content, flags=re.DOTALL)

            # Write modified content to the final file
            with open(filename, 'w') as f:
                f.write(content)

            # Remove the temporary file
            os.unlink(temp_filename)

        # Replace the write method
        pst.write = custom_write.__get__(pst)

        # ~~~~~~~~/ Add LSQR section as a custom attribute

        # Set additional control data parameters
        pst.control_data.rlambda1 = 10.0
        pst.control_data.numlam = 10
        pst.control_data.icov = 1
        pst.control_data.icor = 1
        pst.control_data.ieig = 1

        # Add the the command used to run the model executable
        pst.model_command = [model_comand_line]

        # Add number of iteractions
        pst.control_data.noptmax = noptmax

        # Validate output_path
        output_path = validate_output_path(output_path)

        # Create the path and name for the file ouput
        pst_file_path = os.path.join(output_path, pst_filename)

        # Write the PST file
        pst.write(pst_file_path)

        print(f"PST file successfully created: {pst_file_path}")

    except ValueError as ve:
        print(f"ValueError: {ve}")
    # except FileNotFoundError as fe:
    #     print(f"FileNotFoundError: {fe}")
    # except Exception as e:
    #     print(f"An unexpected error occurred: {e}")