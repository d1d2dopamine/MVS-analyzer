# Run via Colab

Colab is optional cloud computation using Google's service. Local analysis remains available without it. Only upload data you are permitted to process there.

## Start a job

1. Load data and choose the calculation in MVS, then select **Run via Colab / Запустить через Colab**.
2. Approve transfer of that job. Keep the desktop application open.
3. Run the notebook's first cell. On first pairing, paste the connection code copied by MVS into the hidden prompt and allow the browser's local-network permission if requested.
4. Use the second cell for analysis and the third cell to download the results ZIP.

The first cell prepares the selected operation and performs standard calibration. Additional models run in the second cell. A verified matching calibration is reused rather than repeated.

## Reusing a notebook

A live paired notebook can be reopened for another job. Run its first cell to accept the newly selected job. Matching includes data, preprocessing, statistical settings and repetition count. A changed job must not reuse an incompatible calibration.

An open browser tab alone does not mean a kernel is still running. Google controls runtime availability and session duration. MVS can track notebooks paired with the application, not every notebook in your Google account.

If address detection fails, enter the saved `https://colab.research.google.com/drive/...` address in the notebook's **Notebook URL** field. You do not need to make the notebook public.

## Manual file exchange

If browser policy blocks the local connection, use the job ZIP shown by MVS. Leave the notebook connection prompt empty and upload that ZIP. After computation, download the results ZIP and choose **Import Colab result** with the matching data and settings loaded in MVS.

Standalone CSV/TSV upload is also available. Synthetic estimation and benchmark studies do not require a measurement file.

## Saved calibration and errors

Use the current application and notebook together; an old application may carry an older analyzer in its exported job. The notebook shows the application and engine versions before running.

Compatible saved calibration from Windows or Linux is verified before reuse. Updating line-ending-dependent legacy fingerprints does not repeat simulations or change their numerical results. Corrupted files, mismatched data/settings or incompatible methods are rejected, not silently repaired or overwritten.

If checksum verification still fails, keep the original state and result ZIP for diagnosis. Do not edit the checksum manually. Re-export a verified job from the updated application or choose a fresh calibration if the original file is genuinely damaged.

## Privacy

The job includes its measurements. Results omit the source job and connection code but may still contain sensitive reports. Clear notebook outputs before sharing; never publish an active connection code. MVS does not request your Google password or API secrets.
