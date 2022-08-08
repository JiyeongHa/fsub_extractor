import os.path as op
import os
import shutil
import subprocess


def find_program(program):
    """Checks that a command line tools is on accessible on PATH
    Parameters
    ==========
    program: str
            name of command to look for 

    Outputs
    =======
    program: str
            returns the program if found, and errors out if not found
    """

    #  Simple function for checking if a program is executable
    def is_exe(fpath):
        return op.exists(fpath) and os.access(fpath, os.X_OK)

    path_split = os.environ["PATH"].split(os.pathsep)
    if len(path_split) == 0:
        raise SystemExit("PATH environment variable is empty.")

    for path in path_split:
        path = path.strip('"')
        exe_file = op.join(path, program)
        if is_exe(exe_file):
            return program
        else:
            raise SystemExit("Command " + function_name + " could not be found in PATH.")


def run_command(cmd_list):
    """Interface for running CLI commands in Python.
    Crashes if command returns an error
    Parameters
    ==========
    cmd_list: list
            List containing arguments for the function, e.g. ['Command Name', '--argName1', 'arg1']

    Outputs
    =======
    None
    """

    function_name = cmd_list[0]
    return_code = subprocess.run(cmd_list).returncode
    if return_code != 0:
       raise SystemExit("Command " + function_name + " exited with errors. See message above for more information.")


def merge_rois(roi1, roi2, outpath_base):
    """Creates the input ROI atlas-like file to be passed into tck2connectome.
    If a single ROI file is passed:
            Copies the same single ROI file.
    If multiple ROI files are passed:
            Multiplies the second ROI file passed by 2, and merges this file with the first file.
            Returns the merged file
    Parameters
    ==========
    roi1: str
            abspath to a roi mask file
    roi2: str
            abspath to a second roi mask file

    Outputs
    =======
    Function returns None
    
    """

    labelled_roi2 = roi2.removesuffix(".nii.gz") + "_labelled.nii.gz"
    mrcalc = find_program("mrcalc")

    # Multiply second ROI by 2
    cmd_mrcalc_mult = [mrcalc, roi2, "2", "-mult", labelled_roi2]
    run_command(cmd_mrcalc_mult)

    # Merge ROIs
    cmd_mrcalc_merge = [mrcalc, roi1, labelled_roi2, "-add", out_file]
    run_command(cmd_mrcalc_merge)

    return None


def anat_to_gmwmi(anat, outpath_base):
    """Creates a gray-matter-white-matter-interface (GMWMI) from a T1 or FreeSurfer image
    If a T1 image is passed (not recommended), uses FSL FAST to create 5TT and GMWMI
    If a FreeSurfer directory is passed in, uses the surface reconstruction to create 5TT and GMWMI

    Parameters
    ==========
    anat: str
            Either a path to a T1 image (.nii, .nii.gz, .mif) or FreeSurfer output directory
    outpath_base: str
            Path to output directory, including output prefix
            

    Outputs
    =======
    Function returns None
    outpath_base + 5tt.nii.gz is the 5TT segmented anatomical image
    outpath_base + gmwmi.nii.gz is the GMWMI image
    """

    # Check for T1 file vs FreeSurfer directory
    if op.isdir(op.join(anat,'surf')):
         print('FreeSurfer input detected: Using 5ttgen HSVS algorithm to generate GMWMI')
         fivett_algo = 'hsvs'
    elif anat[-7:] == '.nii.gz' or anat[-4:] == '.nii' or anat[-4:] == '.mif':
         print('T1 image detected: Using default FSL 5ttgen algorithm to generate GMWMWI')
         fivett_algo = 'fsl'
    else:
         raise Exception("Neither T1 or FreeSurfer input detected; Unable to create GMWMI")

    # Run 5ttgen to generate 5tt image
    print('Generating 5TT Image')
    fivettgen = find_program("5ttgen")
    cmd_5ttgen = [fivettgen, fivett_algo, anat, outpath_base + '5tt.nii.gz', '-nocrop']
    run_command(cmd_5ttgen)

    # Run 5tt2gmwmi to generate GMWMI image
    print('Generating GMWMI Image')
    fivett2gmwmi = find_program("5tt2gmwmi")
    cmd_5tt2gmwmi = [fivett2gmwmi, outpath_base + '5tt.nii.gz', outpath_base + 'gmwmi.nii.gz']
    run_command(cmd_5tt2gmwmi)
    print('Finished creating GMWMI')

    return None


def extract_tck_mrtrix(tck_file, rois_in, outpath_base, search_dist, two_rois):
    """Uses MRtrix tools to extract the TCK file that connects to the ROI(s)
    If the ROI image contains one value, finds all streamlines that connect to that region
    If the ROI image contains two values, finds all streamlines that connect the two regions

    Parameters
    ==========
    tck_file: str
            Path to the input tractography file (.tck)
    rois_in: str
            Atlas-like image (.nii.gz, .nii., .mif) containing all ROIs, each with different intensities
    outpath_base: str
            Path to output directory, including output prefix
    search_dist: float
            How far to search ahead of streamlines for ROIs, in mm
    two_rois: bool
            True if two ROIs in rois_in, False, if one ROI in rois_in
            

    Outputs
    =======
    Function returns None
    outpath_base + 5tt.nii.gz is the 5TT segmented anatomical image
    outpath_base + gmwmi.nii.gz is the GMWMI image
    """

    ### tck2connectome
    tck2connectome = find_program("tck2connectome")
    tck2connectome_cmd = [
            tck2connectome,
            tck_file,
            rois_in,
            outpath_base + "connectome.txt",
            "-assignment_forward_search",
            search_dist,
            "-out_assignments",
            outpath_base + "assignments.txt",
            "-force"
        ]
    run_command(tck2connectome_cmd)

    ### connectome2tck
    connectome2tck = find_program("connectome2tck")
    # Change connectome2tck arguments based on single node or pairwise nodes
    if two_rois:
        nodes = "1,2"
    else:
        nodes = "0,1"
    connectome2tck_cmd = [
            connectome2tck,
            tck_file,
            outpath_base + "assignments.txt",
            outpath_base + "extracted",
            "-nodes",
            nodes,
            "-exclusive",
            "-files",
            "single"
        ]
    run_command(connectome2tck_cmd)

    return None


def dilate_roi(roi_in, fs_dir, hemi, outpath_base):
    #Change the environment to set FreeSurfer SUBJECTS_DIR
    #my_env = os.environ.copy()
    #my_env["SUBJECTS_DIR"] = "/usr/sbin:/sbin:" + my_env["PATH"]
	#subprocess.Popen(my_command, env=my_env)
    #os.environ["SUBJECTS_DIR"] = "1"
    subject = fs_dir.split('/')[-1]
    roi_file_extension = roi_in.split('.')[-1]
    if roi_file_extension != 'label' and roi_file_extension != 'mgz':
        print('Using volumetric ROI dilation pipeline')
        roi_surf = roi_in.replace(roi_file_extension,'.mgz')
        #tkregister2 = find_program('tkregister2')
        #tkregister2_cmd = [tkregister2, '--mov', op.join(fs_dir, 'mri','orig.mgz'), '--noedit', '--s', subject, '--regheader', '--reg', op.join(fs_dir,'surf','register.dat')]
        #run_command(tckregister2_cmd)
        mri_vol2surf = find_program('mri_vol2surf')
        mri_vol2surf_cmd = [mri_vol2surf, '--src', roi_in, '--projfrac-max', '-.5 1 .1', '--out', roi_surf, '--regheader', subject, '--hemi', hemi]
        run_command(mri_vol2surf_cmd)
    else:
        roi_surf = roi_in
        print('Starting with surface ROI')

    mri_surf2vol = find_program('mri_surf2vol')
    mri_surf2vol_cmd = [mri_surf2vol, '--surfval', roi_surf, '--o', roi_in, 
            '--subject', subject, '--fill-projfrac', '-2 0 0.05', '--hemi', hemi, '--template', op.join(fs_dir, 'mri', 'aseg.mgz'), '--identity', subject]
    run_command(mri_surf2vol)
    return None # EVENTUALLY RETURN PATH TO FINAL ROI


def intersect_gmwmi(rois_in, gmwmi, outpath_base):
    mrcalc = find_program("mrcalc")
    mrcalc_cmd = [mrcalc_path, rois_in, gmwmi, "-mult", outpath_base + 'gmwmi_roi_intersect.nii.gz']
    run_command(mrcalc_cmd)

