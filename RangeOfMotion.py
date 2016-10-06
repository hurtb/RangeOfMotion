from functools import partial
import time
import numpy as np
from __main__ import vtk, qt, ctk, slicer
import RangeOfMotionLib as motion


class RangeOfMotion:
    def __init__(self, parent):
        parent.title = "Range of Motion"
        parent.categories = ["Spine Toolbox"]
        parent.dependencies = []
        parent.contributors = ["Brian Hurt (University of Colorado School of Medicine)",
                               "Christopher Cain (University of Colorado Department of Spine Orthopedics)"]
        parent.helpText = """
        This module computes the relative range of motion between two models.

        User inputs 2 existing surface models, sets some initial conditions (e.g. setting an implant), sets simulation
        parameters, and then runs a simulation to determine the mechanical range of motion between the two models.

        This is developed to compute the flexion and extension properties of two adjacent vertebrae.
        """
        parent.acknowledgementText = """
        """  # replace with organization, grant and thanks.

        parent.icon = qt.QIcon("%s/arrow.png" % motion.ICON_DIR)

        self.parent = parent


class RangeOfMotionWidget():

    def __init__(self, parent=None, *args):
        # super(RangeOfMotionWidget, self).__init__(*args)
        self.models = []  # collection of models
        self.sims = []  # collection of simulations
        self.logic = RangeOfMotionLogic()
        if not parent:
            self.parent = slicer.qMRMLWidget()
            self.parent.setLayout(qt.QVBoxLayout())
            self.parent.setMRMLScene(slicer.mrmlScene)
        else:
            self.parent = parent
        self.layout = self.parent.layout()
        if not parent:
            self.setup()
            self.parent.show()
        # self.setup()

    def setup(self):
        input_frame = self.input_frame = qt.QFrame()
        input_frame.setLayout(qt.QHBoxLayout())


        def _add_modelsUI():
            modelsCollapsibleButton = self.modelsCollapsibleButton = ctk.ctkCollapsibleButton()
            modelsCollapsibleButton.text = "Position Vertebrae && Create Implant(s)"
            modelsCollapsibleButton.enabled = True
            modelsCollapsibleButton.collapsed = True
            self.layout.addWidget(modelsCollapsibleButton)
            # Layout within the path collapsible button
            modelsFormLayout = qt.QFormLayout(modelsCollapsibleButton)
            boneModelFrame = self.boneModelFrame = ctk.ctkCollapsibleGroupBox()
            boneModelFrame.title = "Bone Models"
            boneModelFrame.collapsed = False
            boneModelFrame.setLayout(qt.QVBoxLayout())
            modelsFormLayout.layout().addWidget(boneModelFrame)

            self.modelTable = motion.ModelTableWidget(modelsFormLayout, width=motion.MODEL_TABLE_WIDTH,
                                                      height=motion.MODEL_TABLE_HEIGHT, orientation="C")
            self.add_model_widget(self.boneModelFrame)  # Model input 1, in self.models[]
            self.add_model_widget(self.boneModelFrame)  # Model input 2, in self.models[]
            self.modelTable.widget.setHorizontalHeaderLabels(["Bone 1", "Bone 2"])

            self.boneModelFrame.layout().addWidget(self.modelTable.widget)

            implantModelFrame = self.implantModelFrame = ctk.ctkCollapsibleGroupBox()
            implantModelFrame.title = "Implant Models (optional)"
            implantModelFrame.collapsed = True
            implantModelFrame.setLayout(qt.QVBoxLayout())
            modelsFormLayout.layout().addWidget(implantModelFrame)

            # Implants
            inputImplantFrame = qt.QFrame()
            inputImplantFrame.setLayout(qt.QVBoxLayout())
            implantWidget = self.implantWidget = motion.ImplantWidget()
            implantModelFrame.layout().addWidget(implantWidget)

            # Collision Simulation
            colFrame = qt.QFrame()
            colFrame.setLayout(qt.QHBoxLayout())
            colButtonFrame = qt.QFrame()
            colButtonFrame.setLayout(qt.QVBoxLayout())
            colFrame.layout().addWidget(colButtonFrame)

            colOutMsgFrame = qt.QFrame()
            colOutMsgFrame.setLayout(qt.QVBoxLayout())
            colFrame.layout().addWidget(colOutMsgFrame)

            colButtonLabelText = "Check Collision"
            colButton = qt.QPushButton(colButtonLabelText)
            colButton.setStyleSheet("background-color: #95DB9A")
            colButtonFrame.layout().addWidget(colButton)
            self.colButton = colButton

            collisionViewBox = self.collisionViewBox = qt.QCheckBox("View Collision")
            colButtonFrame.layout().addWidget(collisionViewBox)

            clearSimButton = qt.QPushButton("Reset")
            clearSimButton.toolTip = "Reset the module"
            clearSimButton.enabled = True
            clearSimButton.setStyleSheet("background-color: #95DB9A")
            colButtonFrame.layout().addWidget(clearSimButton)
            self.clearSimButton = clearSimButton

            colOutLabel = qt.QLabel("Output Message")
            colOutMsgFrame.layout().addWidget(colOutLabel)
            self.colOutMsg = qt.QTextEdit()
            self.colOutMsg.setReadOnly(True)
            colOutMsgFrame.layout().addWidget(self.colOutMsg)
            modelsFormLayout.layout().addWidget(colFrame)

        def _add_simUI():
            # Simulation Settings
            self.simCollapseButton = ctk.ctkCollapsibleButton()
            self.simCollapseButton.text = "Create && Run Range of Motion Simulations"
            self.simCollapseButton.setToolTip("Evaluate the range of motion. ")
            self.simCollapseButton.enabled = True
            self.simCollapseButton.collapsed = True
            self.layout.addWidget(self.simCollapseButton)
            simFormLayout = qt.QFormLayout(self.simCollapseButton)  # Layout within the collapsible button
            # addButton = self.addButton = qt.QPushButton("+")
            # delButton = self.delButton = qt.QPushButton("-")
            btnSimFrame = qt.QFrame()
            btnSimFrame.setLayout(qt.QHBoxLayout())
            # btnSimFrame.layout().addWidget(addButton)
            # btnSimFrame.layout().addWidget(delButton)
            simFormLayout.layout().addWidget(btnSimFrame)

            simTable = self.simTable = motion.SimTableWidget(simFormLayout, width=motion.SIM_TABLE_WIDTH,
                                                             height=motion.SIM_TABLE_HEIGHT, orientation="C",
                                                             layout=motion.SIM_TABLE_PROPS)
            self.add_sim_widget(self.boneModelFrame)  # Sim input 1, in self.model_widget
            self.simTable.widget.setHorizontalHeaderLabels(["Sim 1"])
            simFormLayout.layout().addWidget(simTable.widget)

        _add_modelsUI()
        _add_simUI()
        # self.layout.setLayout(layout)
        self.layout.addWidget(input_frame)

        class state(object):
            bones = [motion.ModelState() for model in self.models]
            intersectionNodes = []
            # auto_update = self.updateModelButton.isChecked()
            implant_list = []
            implant = None
            view_collision = False

            @classmethod
            def is_valid(cls):
                print [bone_st.is_valid() for bone_st in cls.bones]
                return all(bone_st.is_valid() for bone_st in cls.bones)

        def initializeModelNode(node):
                displayNode = slicer.vtkMRMLModelDisplayNode()
                storageNode = slicer.vtkMRMLModelStorageNode()
                displayNode.SetScene(slicer.mrmlScene)
                storageNode.SetScene(slicer.mrmlScene)
                slicer.mrmlScene.AddNode(displayNode)
                slicer.mrmlScene.AddNode(storageNode)
                node.SetAndObserveDisplayNodeID(displayNode.GetID())
                node.SetAndObserveStorageNodeID(storageNode.GetID())

        scope_locals = locals()

        def connect(obj, evt, cmd):
            def callback(*args):
                current_locals = scope_locals.copy()
                current_locals.update({'args': args})
                exec cmd in globals(), current_locals
                updateGUI()
            obj.connect(evt, callback)

        def updateGUI():

            def button_stylesheet(active):
                if active:
                    return "background-color: #95DB9A"
                else:
                    return ""
            state.bones = [model.state for model in self.models]
            if state.intersectionNodes:
                for node in state.intersectionNodes:
                    node.GetModelDisplayNode().SetVisibility(state.view_collision)

            if state.is_valid():
                slicer.app.processEvents()
                self.logic.update(state)
            else:
                print "invalid state\n------"

        def initialize():

            for sim in self.sims:
                sim.implantBox.setImplantWidgetSource(self.implantWidget)
            # connect to ModelWidget objects
            for i in range(len(self.models)):
                connect(self.models[i], 'customContextMenuRequested(QPoint*)', 'updateGUI')

            self.colButton.connect('clicked()', onApply)
            self.clearSimButton.connect('clicked()', onClearSim)
            connect(self.collisionViewBox, 'stateChanged(int)', 'state.view_collision = False if args[0]==0 else True')
            # connect(self.implantWidget.implantModelView, 'clicked()', 'updateImplantList')

        def onApply():
            # update GUI
            print "In ROM Object"
            updateGUI()
            og_text = self.colButton.text
            self.colButton.text = "Working..."
            self.colButton.setStyleSheet("background-color: #FA6161")
            self.colButton.repaint()
            slicer.app.processEvents()

            # Send sub_mod states to their proper 'onApply' method
            self.logic = RangeOfMotionLogic()
            self.logic.update(state)
            collision, result, msg = self.logic.check_collisions()

            # Adjust # of collision Model Nodes
            diff = len(collision.vtkIntersectionPolyDataFilters) > len(state.intersectionNodes)
            modNinterModelNodes(diff)
            for i, inter in enumerate(collision.vtkIntersectionPolyDataFilters):  # update/create model for slicer
                node = state.intersectionNodes[i]
                node.SetAndObservePolyData(inter.GetOutput(0))
                node.SetName("Collision %s" % (i+1))

            if self.collisionViewBox.checked:  # view intersection outline
                for node in state.intersectionNodes:  # update/create model for slicer
                    node.GetModelDisplayNode().SetVisibility(True)
            else:
                for node in state.intersectionNodes:  # update/create model for slicer
                    node.GetModelDisplayNode().SetVisibility(False)

            self.colButton.setStyleSheet("background-color: #95DB9A")
            self.colButton.text = og_text
            self.colOutMsg.setText(msg)

        def onClearSim():
            updateGUI()
            self.clearSimButton.text = "Clearing..."
            self.clearSimButton.setStyleSheet("background-color: #FA6161")
            self.logic.reset(state)
            self.clearSimButton.text = "Clear Simulation"
            self.clearSimButton.setStyleSheet("background-color: #95DB9A")

        def updateImplantList():
            state.implant_list = [item.text() for item in self.implantWidget.implantModelView.items]
            self.simTable.updateImplantList(state.implant_list)
        self.implantWidget.implantModelView.clicked.connect(updateImplantList)
        self.implantWidget.createButton.clicked.connect(updateImplantList)

        def modNinterModelNodes(diff):
            if diff > 0:
                _addNinterModelNodes(diff)
            elif diff < 0:
                _rmNinterModelNodes(diff)

        def _addNinterModelNodes(N=0):
            for i in range(N):
                displayNode = slicer.vtkMRMLModelDisplayNode()
                slicer.mrmlScene.AddNode(displayNode)
                interModel = slicer.vtkMRMLModelNode()
                slicer.mrmlScene.AddNode(interModel)
                interModel.SetAndObserveDisplayNodeID(displayNode.GetID())
                state.intersectionNodes.append(interModel)

        def _rmNinterModelNodes(N=0):
            for n in range(N):
                node = state.intersectionNodes[-n]
                slicer.mrmlScene.RemoveNode(node)
                state.intersectionNodes.pop()

        initialize()
        updateGUI()
        self.updateGUI = updateGUI

    def add_model_widget(self, parent):
        # Model input row
        my_row = len(self.models)
        tmp_model = motion.ModelWidget.ModelWidget("Model %d" % (my_row + 1), None)
        tmp_model.organize_table_row()
        self.models.append(tmp_model)
        self.modelTable.add_model(tmp_model, index=my_row)

    def add_sim_widget(self, parent, implantState=None):
        # Model input row
        my_row = len(self.sims)
        tmp_sim = motion.SimWidget()
        tmp_sim.organize_table_row()
        self.sims.append(tmp_sim)
        self.simTable.add_model(tmp_sim, index=my_row)


class RangeOfMotionLogic:
    """Map the Slicer inputs to the library to perform the simulation
    """
    def __init__(self):
        self.dynamics = motion.BoneDynamics()
        self.collision = motion.Intersection()
        self.state = motion.ModelState()

    def update(self, state):
        self.state = state
        # update bones using the transformed polydata
        bones = [motion.Bone(bone.output_node.GetPolyData(), name=bone.model_name, fixed=bone.fixed)
                 for bone in state.bones if bone.is_valid()]
        self.dynamics.add_bones(bones)

        # update the implants

    def check_collisions(self, reset_rotation=True):
        start = time.clock()
        inters = self.dynamics.update_collisions()  # get intersection object
        if inters.total_bone_collisions > 0:
            outmsg = "There are %d collisions" % inters.total_bone_collisions \
                if inters.total_bone_collisions > 1 else "There is 1 collision"
        else:
            outmsg = "There are no collisions"
        elapsed = (time.clock() - start)
        return inters, True, "%s\nCompleted in %0.2f s" % (outmsg, elapsed)

    def reset(self, state):
        self.dynamics.reset()
        for i in range(len(state.modelNode)):
            state.modelNode[i].SetAndObservePolyData(self.dynamics.original_bones[i].polydata)