from glob import glob
import setuptools

setuptools.setup(
    name="gdadorn",
    version='0.1.0',
    url="",
    author="similarface",
    EMAIL='similarface@gmail.com',
    description="jupyer的一些扩展修改，内存显示，下载限制等等",
    packages=setuptools.find_packages(),
    install_requires=[
        'psutil',
        'notebook',
    ],
    data_files=[
        ('share/jupyter/nbextensions/gdadorn', glob('gdadorn/static/*')),
        ('etc/jupyter/jupyter_notebook_config.d', ['gdadorn/etc/serverextension.json']),
        ('etc/jupyter/nbconfig/notebook.d', ['gdadorn/etc/nbextension.json'])
    ],
    zip_safe=False,
    include_package_data=True
)
